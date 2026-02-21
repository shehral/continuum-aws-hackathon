"""Bulk import/export endpoints for decisions (PRODUCT-P2-5).

Provides JSON import/export functionality for decisions with user isolation.
All operations respect user boundaries - users can only export their own data.
"""

from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from neo4j.exceptions import ClientError, DatabaseError, DriverError
from pydantic import BaseModel, Field, field_validator

from db.neo4j import get_neo4j_session
from routers.auth import get_current_user_id
from utils.cache import invalidate_user_caches
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class DecisionImportItem(BaseModel):
    """Schema for a single decision in import payload."""

    trigger: str = Field(..., min_length=1, max_length=5000)
    context: str = Field(..., min_length=1, max_length=10000)
    options: list[str] = Field(..., min_length=1, max_length=50)
    decision: str = Field(..., min_length=1, max_length=5000)
    rationale: str = Field(..., min_length=1, max_length=10000)
    confidence: float = Field(0.8, ge=0.0, le=1.0)
    source: str = Field("import", max_length=50)
    entities: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("options")
    @classmethod
    def validate_options(cls, v: list[str]) -> list[str]:
        """Validate each option string."""
        if not v:
            raise ValueError("At least one option is required")
        validated = []
        for opt in v:
            if not opt or len(opt) > 1000:
                raise ValueError("Each option must be 1-1000 characters")
            validated.append(opt.strip())
        return validated


class BulkImportRequest(BaseModel):
    """Request body for bulk import."""

    decisions: list[DecisionImportItem] = Field(..., min_length=1, max_length=500)
    skip_duplicates: bool = Field(
        True,
        description="If true, skip decisions that match existing ones by trigger+decision",
    )


class BulkImportResult(BaseModel):
    """Response for bulk import operation."""

    status: str
    imported: int
    skipped: int
    errors: list[dict]
    decision_ids: list[str]


class ExportDecision(BaseModel):
    """Export format for a decision (simplified for portability)."""

    trigger: str
    context: str
    options: list[str]
    decision: str
    rationale: str
    confidence: float
    source: str
    created_at: str
    entities: list[dict]
    verbatim_quote: Optional[str] = None
    verbatim_start_char: Optional[int] = None
    verbatim_end_char: Optional[int] = None
    turn_index: Optional[int] = None


class BulkExportResult(BaseModel):
    """Response for bulk export operation."""

    exported_at: str
    total_decisions: int
    decisions: list[ExportDecision]


@router.post("/import", response_model=BulkImportResult)
async def bulk_import_decisions(
    request: BulkImportRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Import multiple decisions from JSON.

    PRODUCT-P2-5: Bulk import functionality.

    - Accepts up to 500 decisions per request
    - Creates entities automatically from entity names
    - Optionally skips duplicates (matched by trigger + decision text)
    - All imported decisions are owned by the current user
    """
    imported_count = 0
    skipped_count = 0
    errors = []
    decision_ids = []

    session = await get_neo4j_session()
    async with session:
        for idx, item in enumerate(request.decisions):
            try:
                # Check for duplicates if skip_duplicates is enabled
                if request.skip_duplicates:
                    result = await session.run(
                        """
                        MATCH (d:DecisionTrace)
                        WHERE d.user_id = $user_id
                          AND d.trigger = $trigger
                          AND COALESCE(d.agent_decision, d.decision) = $decision
                        RETURN d.id as id
                        LIMIT 1
                        """,
                        user_id=user_id,
                        trigger=item.trigger,
                        decision=item.decision,
                    )
                    record = await result.single()
                    if record:
                        skipped_count += 1
                        continue

                # Create the decision
                decision_id = str(uuid4())
                created_at = datetime.now(UTC).isoformat()

                await session.run(
                    """
                    CREATE (d:DecisionTrace {
                        id: $id,
                        trigger: $trigger,
                        context: $context,
                        options: $options,
                        decision: $decision,
                        rationale: $rationale,
                        confidence: $confidence,
                        created_at: $created_at,
                        source: $source,
                        user_id: $user_id
                    })
                    """,
                    id=decision_id,
                    trigger=item.trigger,
                    context=item.context,
                    options=item.options,
                    decision=item.decision,
                    rationale=item.rationale,
                    confidence=item.confidence,
                    created_at=created_at,
                    source=item.source or "import",
                    user_id=user_id,
                )

                # Create and link entities
                for entity_name in item.entities:
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

                decision_ids.append(decision_id)
                imported_count += 1

            except Exception as e:
                logger.error(f"Error importing decision at index {idx}: {e}")
                errors.append(
                    {
                        "index": idx,
                        "trigger": item.trigger[:50] + "..."
                        if len(item.trigger) > 50
                        else item.trigger,
                        "error": str(e),
                    }
                )

    # Invalidate caches since data changed
    if imported_count > 0:
        await invalidate_user_caches(user_id)

    logger.info(
        f"Bulk import for user {user_id}: "
        f"imported={imported_count}, skipped={skipped_count}, errors={len(errors)}"
    )

    return BulkImportResult(
        status="completed",
        imported=imported_count,
        skipped=skipped_count,
        errors=errors,
        decision_ids=decision_ids,
    )


@router.get("/export", response_model=BulkExportResult)
async def bulk_export_decisions(
    source_filter: Optional[str] = Query(
        None,
        description="Filter by source (claude_logs, interview, manual, import, unknown)",
    ),
    limit: int = Query(1000, ge=1, le=10000),
    user_id: str = Depends(get_current_user_id),
):
    """Export all user's decisions as JSON.

    PRODUCT-P2-5: Bulk export functionality.

    - Returns all decisions owned by the current user
    - Includes all entity relationships
    - Optionally filter by source type
    - Maximum 10,000 decisions per export
    """
    try:
        session = await get_neo4j_session()
        async with session:
            # Build query with optional source filter
            where_clause = "WHERE d.user_id = $user_id OR d.user_id IS NULL"
            if source_filter:
                where_clause += " AND d.source = $source_filter"

            query = f"""
                MATCH (d:DecisionTrace)
                {where_clause}
                OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
                WITH d, collect(e) as entities
                ORDER BY d.created_at DESC
                LIMIT $limit
                RETURN d, entities, d.verbatim_decision, d.verbatim_trigger, d.decision_span, d.turn_index
            """

            params = {
                "user_id": user_id,
                "limit": limit,
            }
            if source_filter:
                params["source_filter"] = source_filter

            result = await session.run(query, **params)

            decisions = []
            async for record in result:
                d = record["d"]
                entities = record["entities"]

                # Extract verbatim fields
                verbatim_quote = d.get("verbatim_decision") or d.get("verbatim_trigger")
                decision_span = d.get("decision_span")
                verbatim_start_char = None
                verbatim_end_char = None
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
                
                export_decision = ExportDecision(
                    trigger=d.get("trigger", ""),
                    context=d.get("context", ""),
                    options=d.get("options", []),
                    decision=d.get("decision", ""),
                    rationale=d.get("rationale", ""),
                    confidence=d.get("confidence", 0.0),
                    source=d.get("source", "unknown"),
                    created_at=d.get("created_at", ""),
                    entities=[
                        {"name": e["name"], "type": e.get("type", "concept")}
                        for e in entities
                        if e
                    ],
                    verbatim_quote=verbatim_quote,
                    verbatim_start_char=verbatim_start_char,
                    verbatim_end_char=verbatim_end_char,
                    turn_index=d.get("turn_index"),
                )
                decisions.append(export_decision)

            logger.info(
                f"Bulk export for user {user_id}: exported={len(decisions)} decisions"
            )

            return BulkExportResult(
                exported_at=datetime.now(UTC).isoformat(),
                total_decisions=len(decisions),
                decisions=decisions,
            )

    except DriverError as e:
        logger.error(f"Database connection error during export: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")
    except (ClientError, DatabaseError) as e:
        logger.error(f"Error exporting decisions: {e}")
        raise HTTPException(status_code=500, detail="Failed to export decisions")


@router.get("/export/download")
async def download_export(
    source_filter: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
):
    """Download decisions as a JSON file.

    Returns the export with Content-Disposition header for file download.
    """
    export_result = await bulk_export_decisions(
        source_filter=source_filter,
        limit=10000,
        user_id=user_id,
    )

    filename = f"continuum-decisions-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.json"

    return JSONResponse(
        content=export_result.model_dump(),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/json",
        },
    )


@router.post("/export/markdown")
async def export_to_markdown(
    conversation_id: str = Query(..., description="Conversation ID to export"),
    project_name: str = Query("default", description="Project name for export"),
    user_id: str = Depends(get_current_user_id),
):
    """Export decisions and conversation to SpecStory-compatible markdown (Phase 4).
    
    RQ1 Enhancement: SpecStory integration for git-friendly decision traces.
    """
    from services.markdown_exporter import MarkdownExporter
    from services.parser import Conversation
    from db.neo4j import get_neo4j_session
    from fastapi.responses import FileResponse
    
    exporter = MarkdownExporter()
    session = await get_neo4j_session()
    
    async with session:
        # Fetch decisions for this conversation
        result = await session.run(
            """
            MATCH (d:DecisionTrace)
            WHERE d.user_id = $user_id AND d.source = 'claude_logs'
            OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
            WITH d, collect(e.name) as entities
            ORDER BY d.turn_index ASC, d.created_at ASC
            RETURN d, entities
            """,
            user_id=user_id,
        )
        
        decisions = []
        async for record in result:
            d = record["d"]
            # Convert Neo4j node to Decision schema
            from models.schemas import Decision
            decision = Decision(
                id=d.get("id"),
                trigger=d.get("trigger", ""),
                context=d.get("context", ""),
                options=d.get("options", []),
                agent_decision=d.get("agent_decision") or d.get("decision", ""),
                agent_rationale=d.get("agent_rationale") or d.get("rationale", ""),
                confidence=d.get("confidence", 0.5),
                source=d.get("source", "unknown"),
                created_at=d.get("created_at", datetime.now(UTC).isoformat()),
                verbatim_quote=d.get("verbatim_decision") or d.get("verbatim_trigger"),
                verbatim_start_char=d.get("decision_span", {}).get("start_char") if isinstance(d.get("decision_span"), dict) else None,
                verbatim_end_char=d.get("decision_span", {}).get("end_char") if isinstance(d.get("decision_span"), dict) else None,
                turn_index=d.get("turn_index"),
            )
            decisions.append(decision)
        
        # Export to markdown
        file_path = await exporter.export_decisions_to_markdown(
            decisions=decisions,
            conversation_id=conversation_id,
            project_name=project_name,
            conversation_text="",  # Could fetch from conversation store if available
        )
        
        return FileResponse(
            path=str(file_path),
            media_type="text/markdown",
            filename=file_path.name,
        )
