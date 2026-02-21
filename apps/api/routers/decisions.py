"""Decision endpoints with user isolation.

All decisions are isolated by user. Users can only access their own decisions.
Anonymous users can create and view decisions, but they are isolated under
the "anonymous" user_id and not shared across sessions.

SD-024: Cache invalidation added when decisions are created/deleted.
"""

from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j.exceptions import ClientError, DatabaseError, DriverError
from pydantic import BaseModel

from db.neo4j import get_neo4j_session
from models.schemas import Decision, DecisionCreate, DecisionUpdate, Entity
from routers.auth import get_current_user_id
from utils.cache import invalidate_user_caches
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# SEC: Allowlist of fields that can be written to Neo4j properties via update endpoint
ALLOWED_UPDATE_FIELDS = frozenset({
    "trigger", "context", "options", "agent_decision", "agent_rationale",
    "human_decision", "human_rationale",
    "verbatim_quote", "verbatim_start_char", "verbatim_end_char", "turn_index",
})


def _decision_from_record(d, entities) -> Decision:
    """Build a Decision from a Neo4j node dict and entity list."""
    # Extract verbatim fields (support both new structured format and legacy)
    verbatim_quote = None
    verbatim_start_char = None
    verbatim_end_char = None
    
    # Check for verbatim_decision (primary) or verbatim_trigger
    if d.get("verbatim_decision"):
        verbatim_quote = d.get("verbatim_decision")
    elif d.get("verbatim_trigger"):
        verbatim_quote = d.get("verbatim_trigger")
    
    # Extract text span from decision_span (JSON string or dict)
    decision_span = d.get("decision_span")
    if decision_span:
        if isinstance(decision_span, str):
            import json
            try:
                decision_span = json.loads(decision_span)
            except:
                pass
        if isinstance(decision_span, dict):
            verbatim_start_char = decision_span.get("start_char")
            verbatim_end_char = decision_span.get("end_char")
    
    return Decision(
        id=d["id"],
        trigger=d.get("trigger") or "(untitled)",
        context=d.get("context") or "(no context)",
        options=d.get("options", []),
        agent_decision=d.get("agent_decision") or d.get("decision") or "(not recorded)",
        agent_rationale=d.get("agent_rationale") or d.get("rationale") or "(not recorded)",
        human_decision=d.get("human_decision"),
        human_rationale=d.get("human_rationale"),
        confidence=d.get("confidence", 0.0),
        created_at=d.get("created_at", ""),
        entities=[
            Entity(id=e["id"], name=e["name"], type=e.get("type", "concept"))
            for e in entities
            if e
        ],
        source=d.get("source", "unknown"),
        project_name=d.get("project_name"),
        verbatim_quote=verbatim_quote,
        verbatim_start_char=verbatim_start_char,
        verbatim_end_char=verbatim_end_char,
        turn_index=d.get("turn_index"),
    )


class ManualDecisionInput(BaseModel):
    trigger: str
    context: str
    options: list[str]
    decision: str  # backward compat alias — stored as agent_decision
    rationale: str  # backward compat alias — stored as agent_rationale
    entities: list[str] = []  # Entity names to link (optional manual override)
    auto_extract: bool = True  # Whether to auto-extract entities
    project_name: Optional[str] = None  # Project this decision belongs to


@router.get("", response_model=list[Decision])
async def get_decisions(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: str = Depends(get_current_user_id),
):
    """Get all decisions for the current user with pagination.

    Users can only see their own decisions. For backward compatibility,
    decisions without a user_id are visible to all users.
    """
    try:
        session = await get_neo4j_session()
        async with session:
            result = await session.run(
                """
                MATCH (d:DecisionTrace)
                WHERE d.user_id = $user_id OR d.user_id IS NULL
                OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
                WITH d, collect(e) as entities
                ORDER BY d.created_at DESC
                SKIP $offset
                LIMIT $limit
                RETURN d, entities, d.verbatim_decision, d.verbatim_trigger, d.decision_span, d.turn_index
                """,
                user_id=user_id,
                offset=offset,
                limit=limit,
            )

            decisions = []
            async for record in result:
                d = record["d"]
                entities = record["entities"]

                decisions.append(_decision_from_record(d, entities))

            return decisions
    except DriverError as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")
    except (ClientError, DatabaseError) as e:
        logger.error(f"Error fetching decisions: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch decisions")


@router.get("/needs-review", response_model=dict)
async def get_needs_review(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: str = Depends(get_current_user_id),
):
    """Get decisions that need human review (missing human_rationale).

    Returns decisions ordered by confidence descending — high-confidence
    agent decisions are easiest to quickly confirm or override.
    """
    try:
        session = await get_neo4j_session()
        async with session:
            # Get total count
            count_result = await session.run(
                """
                MATCH (d:DecisionTrace)
                WHERE (d.user_id = $user_id OR d.user_id IS NULL)
                  AND d.human_rationale IS NULL
                RETURN count(d) as total
                """,
                user_id=user_id,
            )
            count_record = await count_result.single()
            total = count_record["total"]

            # Get paginated decisions
            result = await session.run(
                """
                MATCH (d:DecisionTrace)
                WHERE (d.user_id = $user_id OR d.user_id IS NULL)
                  AND d.human_rationale IS NULL
                OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
                WITH d, collect(e) as entities
                ORDER BY d.confidence DESC
                SKIP $offset
                LIMIT $limit
                RETURN d, entities, d.verbatim_decision, d.verbatim_trigger, d.decision_span, d.turn_index
                """,
                user_id=user_id,
                offset=offset,
                limit=limit,
            )

            decisions = []
            async for record in result:
                d = record["d"]
                entities = record["entities"]
                decisions.append(_decision_from_record(d, entities))

            return {"total_needs_review": total, "decisions": decisions}
    except DriverError as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")
    except (ClientError, DatabaseError) as e:
        logger.error(f"Error fetching needs-review decisions: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch review queue")


@router.delete("/{decision_id}")
async def delete_decision(
    decision_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a decision by ID.

    Users can only delete their own decisions.
    This removes the decision and all its relationships,
    but preserves the entities it was linked to.
    """
    session = await get_neo4j_session()
    async with session:
        # Check if decision exists AND belongs to the user
        result = await session.run(
            """
            MATCH (d:DecisionTrace {id: $id})
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            RETURN d
            """,
            id=decision_id,
            user_id=user_id,
        )
        record = await result.single()
        if not record:
            # Don't reveal if decision exists but belongs to another user
            raise HTTPException(status_code=404, detail="Decision not found")

        # Delete the decision (DETACH DELETE removes relationships but keeps entities)
        await session.run(
            """
            MATCH (d:DecisionTrace {id: $id})
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            DETACH DELETE d
            """,
            id=decision_id,
            user_id=user_id,
        )

    logger.info(f"Deleted decision {decision_id} for user {user_id}")

    # SD-024: Invalidate caches since data changed
    await invalidate_user_caches(user_id)

    return {"status": "deleted", "id": decision_id}


@router.get("/{decision_id}", response_model=Decision)
async def get_decision(
    decision_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get a single decision by ID.

    Users can only access their own decisions.
    """
    session = await get_neo4j_session()
    async with session:
        result = await session.run(
            """
            MATCH (d:DecisionTrace {id: $id})
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
            WITH d, collect(e) as entities
            RETURN d, entities, d.verbatim_decision, d.verbatim_trigger, d.decision_span, d.turn_index
            """,
            id=decision_id,
            user_id=user_id,
        )

        record = await result.single()
        if not record:
            # Don't reveal if decision exists but belongs to another user
            raise HTTPException(status_code=404, detail="Decision not found")

        d = record["d"]
        entities = record["entities"]

        return _decision_from_record(d, entities)


@router.put("/{decision_id}", response_model=Decision)
async def update_decision(
    decision_id: str,
    update: DecisionUpdate,
    user_id: str = Depends(get_current_user_id),
):
    """Update an existing decision.

    Users can only update their own decisions.
    Only provided fields will be updated. Entity management is handled
    separately via entity linking endpoints.

    Edit history is tracked via edited_at timestamp and edit_count.
    """
    session = await get_neo4j_session()
    async with session:
        # First verify the decision exists and belongs to the user
        result = await session.run(
            """
            MATCH (d:DecisionTrace {id: $id})
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            RETURN d
            """,
            id=decision_id,
            user_id=user_id,
        )
        record = await result.single()
        if not record:
            raise HTTPException(status_code=404, detail="Decision not found")

        # Build the SET clause dynamically based on provided fields
        update_data = update.model_dump(exclude_none=True)
        if not update_data:
            raise HTTPException(
                status_code=400,
                detail="No fields to update. Provide at least one field.",
            )

        # Track edit history
        edited_at = datetime.now(UTC).isoformat()

        # Build Cypher SET clause
        set_parts = [
            "d.edited_at = $edited_at",
            "d.edit_count = COALESCE(d.edit_count, 0) + 1",
        ]
        params = {"id": decision_id, "user_id": user_id, "edited_at": edited_at}

        for field, value in update_data.items():
            if field not in ALLOWED_UPDATE_FIELDS:
                raise HTTPException(
                    status_code=400, detail=f"Field '{field}' cannot be updated"
                )
            # Map alias fields to Neo4j property names
            neo4j_field = field
            if field == "agent_decision":
                neo4j_field = "agent_decision"
            elif field == "agent_rationale":
                neo4j_field = "agent_rationale"
            elif field == "verbatim_quote":
                # Store verbatim_quote in verbatim_decision for consistency
                neo4j_field = "verbatim_decision"
            
            set_parts.append(f"d.{neo4j_field} = ${field}")
            params[field] = value

        set_clause = ", ".join(set_parts)

        # Update the decision
        await session.run(
            f"""
            MATCH (d:DecisionTrace {{id: $id}})
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            SET {set_clause}
            """,
            **params,
        )

        # Fetch and return the updated decision with entities
        result = await session.run(
            """
            MATCH (d:DecisionTrace {id: $id})
            OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
            WITH d, collect(e) as entities
            RETURN d, entities, d.verbatim_decision, d.verbatim_trigger, d.decision_span, d.turn_index
            """,
            id=decision_id,
        )

        record = await result.single()
        d = record["d"]
        entities = record["entities"]

        logger.info(f"Updated decision {decision_id} for user {user_id}")

        # SD-024: Invalidate caches since data changed (e.g. needs_review count)
        await invalidate_user_caches(user_id)

        return _decision_from_record(d, entities)


@router.post("", response_model=Decision)
async def create_decision(
    input: ManualDecisionInput,
    user_id: str = Depends(get_current_user_id),
):
    """Create a decision with automatic entity extraction.

    The decision is linked to the current user for multi-tenant isolation.

    Uses the enhanced extractor with:
    - Few-shot CoT prompts for better entity extraction
    - Entity resolution to prevent duplicates
    - Automatic embedding generation
    - Relationship extraction between entities
    """
    from services.extractor import get_extractor

    # Create DecisionCreate object
    decision_create = DecisionCreate(
        trigger=input.trigger,
        context=input.context,
        options=input.options,
        agent_decision=input.decision,
        agent_rationale=input.rationale,
        source="manual",
        project_name=input.project_name,
    )

    if input.auto_extract:
        # Use the enhanced extractor for automatic entity extraction
        extractor = get_extractor()
        decision_id = await extractor.save_decision(
            decision_create,
            source="manual",
            user_id=user_id,
            project_name=input.project_name
        )
    else:
        # Manual creation without extraction
        decision_id = str(uuid4())
        created_at = datetime.now(UTC).isoformat()

        session = await get_neo4j_session()
        async with session:
            await session.run(
                """
                CREATE (d:DecisionTrace {
                    id: $id,
                    trigger: $trigger,
                    context: $context,
                    options: $options,
                    agent_decision: $agent_decision,
                    agent_rationale: $agent_rationale,
                    confidence: 1.0,
                    created_at: $created_at,
                    source: 'manual',
                    user_id: $user_id,
                    project_name: $project_name
                })
                """,
                id=decision_id,
                trigger=input.trigger,
                context=input.context,
                options=input.options,
                agent_decision=input.decision,
                agent_rationale=input.rationale,
                created_at=created_at,
                user_id=user_id,
                project_name=input.project_name,
            )

            # Create and link manually specified entities
            for entity_name in input.entities:
                if entity_name.strip():
                    entity_id = str(uuid4())
                    await session.run(
                        """
                        MERGE (e:Entity {name: $name})
                        ON CREATE SET e.id = $id, e.type = 'concept'
                        WITH e
                        MATCH (d:DecisionTrace {id: $decision_id})
                        MERGE (d)-[:INVOLVES]->(e)
                        """,
                        id=entity_id,
                        name=entity_name.strip(),
                        decision_id=decision_id,
                    )

    logger.info(f"Created decision {decision_id} for user {user_id}")

    # SD-024: Invalidate caches since data changed
    await invalidate_user_caches(user_id)

    # Fetch and return the created decision with its entities
    session = await get_neo4j_session()
    async with session:
        result = await session.run(
            """
            MATCH (d:DecisionTrace {id: $id})
            OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
            WITH d, collect(e) as entities
            RETURN d, entities
            """,
            id=decision_id,
        )

        record = await result.single()
        d = record["d"]
        entities = record["entities"]

        return _decision_from_record(d, entities)
