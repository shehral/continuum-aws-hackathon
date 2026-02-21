"""Project management endpoints for CRUD operations on projects.

Provides endpoints for listing, viewing, deleting, and resetting projects.
Projects are organizational units for grouping related decisions.
"""

from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db.neo4j import get_neo4j_session
from utils.cache import invalidate_user_caches
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class ProjectStats(BaseModel):
    """Statistics for a single project."""
    name: str
    decision_count: int
    entity_count: int
    created_at: Optional[str] = None
    last_updated: Optional[str] = None
    sources: dict[str, int] = {}


class ProjectListItem(BaseModel):
    """Brief project information for list view."""
    name: str
    decision_count: int
    created_at: Optional[str] = None


@router.get("", response_model=list[ProjectListItem])
async def list_projects():
    """List all projects with basic statistics.

    Returns a list of all projects sorted by decision count (descending).
    Use this to display a project overview table.
    """
    session = await get_neo4j_session()

    async with session:
        result = await session.run(
            """
            MATCH (d:DecisionTrace)
            WHERE d.project_name IS NOT NULL
            WITH d.project_name as name,
                 MIN(d.created_at) as created_at,
                 COUNT(d) as decision_count
            RETURN name, created_at, decision_count
            ORDER BY decision_count DESC
            """
        )

        projects = []
        async for record in result:
            projects.append(
                ProjectListItem(
                    name=record["name"],
                    decision_count=record["decision_count"],
                    created_at=record["created_at"],
                )
            )

        return projects


@router.get("/{name}/stats", response_model=ProjectStats)
async def get_project_stats(name: str):
    """Get detailed statistics for a specific project.

    Returns comprehensive stats including decision count, entity count,
    creation date, last update, and breakdown by source (claude_logs, interview, manual).
    """
    session = await get_neo4j_session()

    async with session:
        # Get decision count and dates
        result = await session.run(
            """
            MATCH (d:DecisionTrace {project_name: $name})
            RETURN COUNT(d) as decision_count,
                   MIN(d.created_at) as created_at,
                   MAX(d.created_at) as last_updated
            """,
            name=name,
        )

        record = await result.single()
        if not record or record["decision_count"] == 0:
            raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

        decision_count = record["decision_count"]
        created_at = record["created_at"]
        last_updated = record["last_updated"]

        # Get entity count (unique entities involved in this project's decisions)
        entity_result = await session.run(
            """
            MATCH (d:DecisionTrace {project_name: $name})-[:INVOLVES]->(e:Entity)
            RETURN COUNT(DISTINCT e) as entity_count
            """,
            name=name,
        )
        entity_record = await entity_result.single()
        entity_count = entity_record["entity_count"] if entity_record else 0

        # Get breakdown by source
        source_result = await session.run(
            """
            MATCH (d:DecisionTrace {project_name: $name})
            RETURN COALESCE(d.source, 'unknown') as source, COUNT(d) as count
            """,
            name=name,
        )

        sources = {}
        async for source_record in source_result:
            sources[source_record["source"]] = source_record["count"]

        return ProjectStats(
            name=name,
            decision_count=decision_count,
            entity_count=entity_count,
            created_at=created_at,
            last_updated=last_updated,
            sources=sources,
        )


@router.delete("/{name}")
async def delete_project(
    name: str,
    confirm: bool = Query(False, description="Must be true to confirm deletion"),
):
    """Delete all decisions in a project.

    WARNING: This permanently deletes all decisions tagged with this project.
    Orphaned entities (not connected to any remaining decisions) will be cleaned up
    automatically by the graph validation service.

    Requires confirmation via ?confirm=true query parameter.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Deletion requires confirmation. Add ?confirm=true to proceed.",
        )

    session = await get_neo4j_session()

    async with session:
        # First, check if project exists
        check_result = await session.run(
            """
            MATCH (d:DecisionTrace {project_name: $name})
            RETURN COUNT(d) as count
            """,
            name=name,
        )
        check_record = await check_result.single()
        if not check_record or check_record["count"] == 0:
            raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

        decisions_count = check_record["count"]

        # Delete all decisions in the project
        # Note: DETACH DELETE removes the node and all its relationships
        await session.run(
            """
            MATCH (d:DecisionTrace {project_name: $name})
            DETACH DELETE d
            """,
            name=name,
        )

        # Clean up orphaned entities (entities not connected to any decisions)
        orphan_result = await session.run(
            """
            MATCH (e:Entity)
            WHERE NOT (e)-[:INVOLVES|SIMILAR_TO|INFLUENCED_BY|SUPERSEDES|CONTRADICTS]-()
            WITH e
            DETACH DELETE e
            RETURN COUNT(e) as orphaned_entities
            """
        )
        orphan_record = await orphan_result.single()
        orphaned_entities = orphan_record["orphaned_entities"] if orphan_record else 0

        # Invalidate caches
        await invalidate_user_caches("anonymous")

        logger.info(
            f"Deleted project '{name}': {decisions_count} decisions, {orphaned_entities} orphaned entities"
        )

        return {
            "status": "deleted",
            "project": name,
            "decisions_deleted": decisions_count,
            "entities_cleaned_up": orphaned_entities,
        }


@router.post("/{name}/reset")
async def reset_project(
    name: str,
    confirm: bool = Query(False, description="Must be true to confirm reset"),
):
    """Reset a project by deleting all its decisions.

    This is the same as DELETE but with a different semantic intent:
    - DELETE: Remove project permanently
    - RESET: Clear project data to prepare for re-import

    Useful when you want to re-import a project from scratch.
    """
    # Reset is the same as delete, just different intent
    result = await delete_project(name, confirm)
    result["status"] = "reset"
    result["message"] = f"Project '{name}' reset. Ready for re-import."
    return result
