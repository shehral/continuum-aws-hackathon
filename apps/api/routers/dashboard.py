"""Dashboard endpoints with proper error handling and caching.

SEC-014: Replaced silent exception handling with specific exception handling and logging.
SD-024: Added Redis caching for dashboard stats (30 second TTL).
"""

from fastapi import APIRouter, Depends, HTTPException
from neo4j.exceptions import AuthError as Neo4jAuthError
from neo4j.exceptions import ServiceUnavailable as Neo4jServiceUnavailable
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.neo4j import get_neo4j_session
from db.postgres import get_db
from models.postgres import CaptureSession
from models.schemas import DashboardStats, Decision, Entity
from utils.cache import get_cached, set_cached
from utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    user_id: str = "anonymous",  # TODO: Wire up real user_id from auth when available
):
    """Get dashboard statistics.

    SEC-014: Proper error handling with specific exceptions and appropriate HTTP responses.
    SD-024: Results are cached in Redis for 30 seconds to reduce database load.
    """
    # SD-024: Check cache first
    cached = await get_cached("dashboard_stats", user_id)
    if cached is not None:
        logger.debug(f"Returning cached dashboard stats for user {user_id}")
        return DashboardStats(**cached)

    # Track what succeeded for partial responses
    total_sessions = 0
    total_decisions = 0
    total_entities = 0
    needs_review = 0
    recent_decisions = []
    errors = []

    # Get session count from PostgreSQL (filtered by user_id)
    try:
        result = await db.execute(
            select(func.count(CaptureSession.id)).where(CaptureSession.user_id == user_id)
        )
        total_sessions = result.scalar() or 0
    except SQLAlchemyError as e:
        logger.error(
            f"PostgreSQL error fetching session count: {type(e).__name__}: {e}",
            exc_info=True,
        )
        errors.append("postgres_sessions")

    # Get Neo4j stats
    try:
        session = await get_neo4j_session()
        async with session:
            # Count decisions
            try:
                result = await session.run(
                    "MATCH (d:DecisionTrace) RETURN count(d) as count"
                )
                record = await result.single()
                total_decisions = record["count"] if record else 0
            except Exception as e:
                logger.error(
                    f"Neo4j error counting decisions: {type(e).__name__}: {e}",
                    exc_info=True,
                )
                errors.append("neo4j_decisions")

            # Count entities
            try:
                result = await session.run("MATCH (e:Entity) RETURN count(e) as count")
                record = await result.single()
                total_entities = record["count"] if record else 0
            except Exception as e:
                logger.error(
                    f"Neo4j error counting entities: {type(e).__name__}: {e}",
                    exc_info=True,
                )
                errors.append("neo4j_entities")

            # Get recent decisions
            try:
                result = await session.run(
                    """
                    MATCH (d:DecisionTrace)
                    OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
                    WITH d, collect(e) as entities
                    ORDER BY d.created_at DESC
                    LIMIT 6
                    RETURN d, entities
                    """
                )

                async for record in result:
                    d = record["d"]
                    entities = record["entities"]

                    decision = Decision(
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
                            Entity(
                                id=e["id"],
                                name=e["name"],
                                type=e.get("type", "concept"),
                            )
                            for e in entities
                            if e
                        ],
                    )
                    recent_decisions.append(decision)
            except Exception as e:
                logger.error(
                    f"Neo4j error fetching recent decisions: {type(e).__name__}: {e}",
                    exc_info=True,
                )
                errors.append("neo4j_recent_decisions")

            # Count decisions needing human review
            try:
                result = await session.run(
                    """
                    MATCH (d:DecisionTrace)
                    WHERE (d.user_id = $user_id OR d.user_id IS NULL)
                      AND d.human_rationale IS NULL
                    RETURN count(d) as count
                    """,
                    user_id=user_id,
                )
                record = await result.single()
                needs_review = record["count"] if record else 0
            except Exception as e:
                logger.error(
                    f"Neo4j error counting needs_review: {type(e).__name__}: {e}",
                    exc_info=True,
                )
                errors.append("neo4j_needs_review")

    except Neo4jServiceUnavailable as e:
        # Neo4j is not available - this is a critical infrastructure issue
        logger.error(f"Neo4j service unavailable: {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Knowledge graph database is currently unavailable. Please try again later.",
        )
    except Neo4jAuthError as e:
        # Authentication failed - configuration issue
        logger.error(f"Neo4j authentication failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Knowledge graph database authentication failed. Please contact support.",
        )
    except Exception as e:
        # Unexpected Neo4j error - log but don't crash
        logger.error(f"Unexpected Neo4j error: {type(e).__name__}: {e}", exc_info=True)
        errors.append("neo4j_connection")

    # If all critical operations failed, return 503
    if len(errors) >= 3:
        logger.error(f"Dashboard stats failed with multiple errors: {errors}")
        raise HTTPException(
            status_code=503,
            detail="Multiple database services are unavailable. Please try again later.",
        )

    # Log partial failures for monitoring
    if errors:
        logger.warning(f"Dashboard stats returned with partial failures: {errors}")

    result = DashboardStats(
        total_decisions=total_decisions,
        total_entities=total_entities,
        total_sessions=total_sessions,
        needs_review=needs_review,
        recent_decisions=recent_decisions,
    )

    # SD-024: Cache the result for 30 seconds
    await set_cached(
        "dashboard_stats",
        user_id,
        result.model_dump(),
        ttl=30,
    )

    return result
