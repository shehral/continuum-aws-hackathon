"""Entity management routes with user isolation and input validation (SEC-005 compliant).

All entity operations are scoped to the current user's data.
Users can only access entities that are connected to their own decisions.

SD-011: Entity lookup cache invalidation on create/update/delete.
"""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from neo4j.exceptions import ClientError, DatabaseError, DriverError

from db.neo4j import get_neo4j_session
from models.schemas import (
    Entity,
    LinkEntityRequest,
    SuggestEntitiesRequest,
)
from routers.auth import get_current_user_id
from services.entity_cache import get_entity_cache
from services.extractor import DecisionExtractor
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


async def _verify_entity_access(session, entity_id: str, user_id: str) -> bool:
    """Verify the user can access this entity.

    An entity is accessible if it's connected to at least one of the user's decisions.
    """
    result = await session.run(
        """
        MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity {id: $entity_id})
        WHERE d.user_id = $user_id OR d.user_id IS NULL
        RETURN count(d) > 0 AS accessible
        """,
        entity_id=entity_id,
        user_id=user_id,
    )
    record = await result.single()
    return record and record["accessible"]


async def _verify_decision_access(session, decision_id: str, user_id: str) -> bool:
    """Verify the user can access this decision."""
    result = await session.run(
        """
        MATCH (d:DecisionTrace {id: $decision_id})
        WHERE d.user_id = $user_id OR d.user_id IS NULL
        RETURN count(d) > 0 AS accessible
        """,
        decision_id=decision_id,
        user_id=user_id,
    )
    record = await result.single()
    return record and record["accessible"]


async def _entity_exists(session, entity_id: str) -> bool:
    """Check if an entity exists (SEC-005)."""
    result = await session.run(
        "MATCH (e:Entity {id: $entity_id}) RETURN count(e) > 0 AS exists",
        entity_id=entity_id,
    )
    record = await result.single()
    return record and record["exists"]


async def _decision_exists(session, decision_id: str) -> bool:
    """Check if a decision exists (SEC-005)."""
    result = await session.run(
        "MATCH (d:DecisionTrace {id: $decision_id}) RETURN count(d) > 0 AS exists",
        decision_id=decision_id,
    )
    record = await result.single()
    return record and record["exists"]


@router.post("/link")
async def link_entity(
    request: LinkEntityRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Link an entity to a decision.

    SEC-005: Input validation ensures:
    - decision_id and entity_id are valid UUIDs
    - relationship is in the allowed whitelist
    - Both the decision and entity exist before linking
    - User owns the decision being linked to
    """
    session = await get_neo4j_session()
    async with session:
        # SEC-005: Verify decision exists
        if not await _decision_exists(session, request.decision_id):
            raise HTTPException(status_code=404, detail="Decision not found")

        # SEC-004: Verify decision belongs to user
        if not await _verify_decision_access(session, request.decision_id, user_id):
            # Don't reveal if decision exists but belongs to another user
            raise HTTPException(status_code=404, detail="Decision not found")

        # SEC-005: Verify entity exists
        if not await _entity_exists(session, request.entity_id):
            raise HTTPException(status_code=404, detail="Entity not found")

        # Create the relationship (relationship type is already validated by Pydantic)
        await session.run(
            """
            MATCH (d:DecisionTrace {id: $decision_id})
            MATCH (e:Entity {id: $entity_id})
            MERGE (d)-[:INVOLVES {relationship: $relationship}]->(e)
            """,
            decision_id=request.decision_id,
            entity_id=request.entity_id,
            relationship=request.relationship,
        )

    logger.info(f"Linked entity {request.entity_id} to decision {request.decision_id}")
    return {"status": "linked"}


@router.post("/suggest", response_model=list[Entity])
async def suggest_entities(
    request: SuggestEntitiesRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Suggest entities to link based on text content.

    Suggestions are based on the user's existing entities plus new extractions.
    """
    extractor = DecisionExtractor()

    # Extract entities from text
    raw_entities = await extractor.extract_entities(request.text)

    # Convert to Entity objects if they're dicts
    entities = []
    for e in raw_entities:
        if isinstance(e, dict):
            entities.append(
                Entity(
                    id=e.get("id"),
                    name=e.get("name", ""),
                    type=e.get("type", "concept"),
                )
            )
        else:
            entities.append(e)

    # Find existing entities that match (scoped to user's entities)
    session = await get_neo4j_session()
    async with session:
        suggestions = []

        for entity in entities:
            # Look for similar existing entities connected to user's decisions
            result = await session.run(
                """
                MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
                WHERE (d.user_id = $user_id OR d.user_id IS NULL)
                AND toLower(e.name) CONTAINS toLower($name)
                RETURN DISTINCT e
                LIMIT 3
                """,
                name=entity.name,
                user_id=user_id,
            )

            async for record in result:
                e = record["e"]
                suggestions.append(
                    Entity(
                        id=e["id"],
                        name=e["name"],
                        type=e.get("type", "concept"),
                    )
                )

        # Add new entities if not found in suggestions
        for entity in entities:
            if not any(s.name.lower() == entity.name.lower() for s in suggestions):
                suggestions.append(entity)

        return suggestions


@router.get("", response_model=list[Entity])
async def get_all_entities(
    user_id: str = Depends(get_current_user_id),
):
    """Get all entities connected to the user's decisions."""
    try:
        session = await get_neo4j_session()
        async with session:
            result = await session.run(
                """
                MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
                WHERE d.user_id = $user_id OR d.user_id IS NULL
                RETURN DISTINCT e
                ORDER BY e.name
                LIMIT 100
                """,
                user_id=user_id,
            )

            entities = []
            async for record in result:
                e = record["e"]
                entities.append(
                    Entity(
                        id=e["id"],
                        name=e["name"],
                        type=e.get("type", "concept"),
                    )
                )

            return entities
    except DriverError as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")
    except (ClientError, DatabaseError) as e:
        logger.error(f"Error fetching entities: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch entities")


@router.post("", response_model=Entity)
async def create_entity(
    entity: Entity,
    user_id: str = Depends(get_current_user_id),
):
    """Create a new entity.

    Note: Entities are shared across users but only visible when
    connected to a user's decisions. Creating an entity doesn't
    automatically connect it to any decision.

    SD-011: Invalidates entity cache on creation.
    """
    cache = get_entity_cache()
    session = await get_neo4j_session()
    async with session:
        # Generate ID if not provided
        entity_id = entity.id or str(uuid4())

        # Check if entity with same name exists
        result = await session.run(
            """
            MATCH (e:Entity)
            WHERE toLower(e.name) = toLower($name)
            RETURN e
            """,
            name=entity.name,
        )
        existing = await result.single()
        if existing:
            # Return existing entity instead of creating duplicate
            e = existing["e"]
            return Entity(id=e["id"], name=e["name"], type=e.get("type", "concept"))

        await session.run(
            """
            CREATE (e:Entity {
                id: $id,
                name: $name,
                type: $type
            })
            """,
            id=entity_id,
            name=entity.name,
            type=entity.type,
        )

        # SD-011: Invalidate cache for any cached lookups with this name
        # This ensures new entity is discoverable
        await cache.invalidate_entity(
            user_id=user_id,
            entity_id=entity_id,
            entity_name=entity.name,
        )
        logger.debug(f"Entity cache invalidated for new entity: {entity.name}")

    return Entity(id=entity_id, name=entity.name, type=entity.type)


@router.get("/{entity_id}", response_model=Entity)
async def get_entity(
    entity_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get a single entity by ID.

    Users can only access entities connected to their decisions.
    """
    session = await get_neo4j_session()
    async with session:
        # Check if entity is accessible to user
        result = await session.run(
            """
            MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity {id: $id})
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            RETURN DISTINCT e
            """,
            id=entity_id,
            user_id=user_id,
        )

        record = await result.single()
        if not record:
            raise HTTPException(status_code=404, detail="Entity not found")

        e = record["e"]
        return Entity(
            id=e["id"],
            name=e["name"],
            type=e.get("type", "concept"),
        )


@router.put("/{entity_id}", response_model=Entity)
async def update_entity(
    entity_id: str,
    entity: Entity,
    user_id: str = Depends(get_current_user_id),
):
    """Update an entity by ID.

    Users can only update entities connected to their decisions.
    SD-011: Invalidates entity cache on update.
    """
    cache = get_entity_cache()
    session = await get_neo4j_session()
    async with session:
        # Check if entity exists and is accessible to user
        result = await session.run(
            """
            MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity {id: $id})
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            RETURN DISTINCT e
            """,
            id=entity_id,
            user_id=user_id,
        )

        record = await result.single()
        if not record:
            raise HTTPException(status_code=404, detail="Entity not found")

        old_entity = record["e"]
        old_name = old_entity.get("name", "")

        # Update the entity
        await session.run(
            """
            MATCH (e:Entity {id: $id})
            SET e.name = $name, e.type = $type
            """,
            id=entity_id,
            name=entity.name,
            type=entity.type,
        )

        # SD-011: Invalidate cache for both old and new names
        await cache.invalidate_entity(
            user_id=user_id,
            entity_id=entity_id,
            entity_name=old_name,
        )
        if entity.name.lower() != old_name.lower():
            await cache.invalidate_entity(
                user_id=user_id,
                entity_id=entity_id,
                entity_name=entity.name,
            )
        logger.debug(f"Entity cache invalidated for updated entity: {entity_id}")

    return Entity(id=entity_id, name=entity.name, type=entity.type)


@router.delete("/{entity_id}")
async def delete_entity(
    entity_id: str,
    force: bool = False,
    user_id: str = Depends(get_current_user_id),
):
    """Delete an entity by ID.

    Users can only delete entities that are ONLY connected to their own decisions.
    If the entity is shared with other users' decisions, deletion is not allowed.

    SD-011: Invalidates entity cache on deletion.

    Args:
        entity_id: The ID of the entity to delete
        force: If True, delete even if entity has relationships with user's decisions.
               If False (default), only delete orphan entities.
    """
    cache = get_entity_cache()
    session = await get_neo4j_session()
    async with session:
        # Check if entity exists and is connected to user's decisions
        result = await session.run(
            """
            MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity {id: $id})
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            RETURN DISTINCT e
            """,
            id=entity_id,
            user_id=user_id,
        )
        record = await result.single()
        if not record:
            raise HTTPException(status_code=404, detail="Entity not found")

        entity_data = record["e"]
        entity_name = entity_data.get("name", "")
        entity_aliases = entity_data.get("aliases", [])

        # Check if entity is connected to other users' decisions
        result = await session.run(
            """
            MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity {id: $id})
            WHERE d.user_id IS NOT NULL AND d.user_id <> $user_id
            RETURN count(d) as other_user_count
            """,
            id=entity_id,
            user_id=user_id,
        )
        record = await result.single()
        if record and record["other_user_count"] > 0:
            raise HTTPException(
                status_code=403,
                detail="Cannot delete entity that is connected to other users' decisions",
            )

        # Check for relationships with user's decisions if not forcing
        if not force:
            result = await session.run(
                """
                MATCH (d:DecisionTrace)-[r:INVOLVES]->(e:Entity {id: $id})
                WHERE d.user_id = $user_id OR d.user_id IS NULL
                RETURN count(r) as rel_count
                """,
                id=entity_id,
                user_id=user_id,
            )
            record = await result.single()
            if record and record["rel_count"] > 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Entity has {record['rel_count']} relationships. Use force=true to delete anyway.",
                )

        # Delete the entity (DETACH DELETE removes all relationships too)
        await session.run(
            "MATCH (e:Entity {id: $id}) DETACH DELETE e",
            id=entity_id,
        )

        # SD-011: Invalidate cache for deleted entity
        await cache.invalidate_entity(
            user_id=user_id,
            entity_id=entity_id,
            entity_name=entity_name,
            aliases=entity_aliases if entity_aliases else None,
        )
        logger.debug(f"Entity cache invalidated for deleted entity: {entity_id}")

    return {"status": "deleted", "id": entity_id}
