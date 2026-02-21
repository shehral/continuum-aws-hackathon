from fastapi import APIRouter, HTTPException, Query
from neo4j.exceptions import ClientError, DatabaseError, DriverError

from db.neo4j import get_neo4j_session
from models.schemas import SearchResult
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class FullTextFallbackError(Exception):
    """Signal to fall back to CONTAINS search when full-text returns no results."""

    pass


@router.get("", response_model=list[SearchResult])
async def search(
    query: str = Query(..., min_length=2),
    type: str = Query(default=None, description="Filter by type: decision or entity"),
):
    """Search decisions and entities using case-insensitive matching."""
    try:
        session = await get_neo4j_session()
        async with session:
            results = []
            search_term = query.lower()

            # Search decisions
            if type is None or type == "decision":
                # Try full-text search first, fall back to CONTAINS
                try:
                    result = await session.run(
                        """
                        CALL db.index.fulltext.queryNodes('decision_fulltext', $search_term)
                        YIELD node, score
                        RETURN node as d, score
                        LIMIT 20
                        """,
                        search_term=query,
                    )
                    found_results = False
                    async for record in result:
                        found_results = True
                        d = record["d"]
                        results.append(
                            SearchResult(
                                type="decision",
                                id=d["id"],
                                label=d.get("trigger", "Decision")[:100],
                                score=record["score"],
                                data={
                                    "trigger": d.get("trigger", ""),
                                    "decision": d.get("decision", ""),
                                    "confidence": d.get("confidence", 0.0),
                                },
                            )
                        )

                    # If no full-text results, fall back to CONTAINS
                    if not found_results:
                        raise FullTextFallbackError()

                except (FullTextFallbackError, ClientError, DatabaseError):
                    # Fall back to case-insensitive CONTAINS
                    result = await session.run(
                        """
                        MATCH (d:DecisionTrace)
                        WHERE toLower(d.trigger) CONTAINS $search_term
                           OR toLower(COALESCE(d.agent_decision, d.decision, '')) CONTAINS $search_term
                           OR toLower(d.context) CONTAINS $search_term
                           OR toLower(COALESCE(d.agent_rationale, d.rationale, '')) CONTAINS $search_term
                        RETURN d, 1.0 as score
                        LIMIT 20
                        """,
                        search_term=search_term,
                    )

                    async for record in result:
                        d = record["d"]
                        results.append(
                            SearchResult(
                                type="decision",
                                id=d["id"],
                                label=d.get("trigger", "Decision")[:100],
                                score=record["score"],
                                data={
                                    "trigger": d.get("trigger", ""),
                                    "decision": d.get("decision", ""),
                                    "confidence": d.get("confidence", 0.0),
                                },
                            )
                        )

            # Search entities
            if type is None or type == "entity":
                # Try full-text search first, fall back to CONTAINS
                try:
                    result = await session.run(
                        """
                        CALL db.index.fulltext.queryNodes('entity_fulltext', $search_term)
                        YIELD node, score
                        RETURN node as e, score
                        LIMIT 20
                        """,
                        search_term=query,
                    )
                    found_results = False
                    async for record in result:
                        found_results = True
                        e = record["e"]
                        results.append(
                            SearchResult(
                                type="entity",
                                id=e["id"],
                                label=e.get("name", "Entity"),
                                score=record["score"],
                                data={
                                    "name": e.get("name", ""),
                                    "type": e.get("type", "concept"),
                                },
                            )
                        )

                    if not found_results:
                        raise FullTextFallbackError()

                except (FullTextFallbackError, ClientError, DatabaseError):
                    # Fall back to case-insensitive CONTAINS
                    result = await session.run(
                        """
                        MATCH (e:Entity)
                        WHERE toLower(e.name) CONTAINS $search_term
                           OR ANY(alias IN COALESCE(e.aliases, []) WHERE toLower(alias) CONTAINS $search_term)
                        RETURN e, 1.0 as score
                        LIMIT 20
                        """,
                        search_term=search_term,
                    )

                    async for record in result:
                        e = record["e"]
                        results.append(
                            SearchResult(
                                type="entity",
                                id=e["id"],
                                label=e.get("name", "Entity"),
                                score=record["score"],
                                data={
                                    "name": e.get("name", ""),
                                    "type": e.get("type", "concept"),
                                },
                            )
                        )

            # Sort by score
            results.sort(key=lambda x: x.score, reverse=True)

            return results
    except DriverError as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")
    except (ClientError, DatabaseError) as e:
        logger.error(f"Search query error: {e}")
        raise HTTPException(status_code=500, detail="Search failed")


@router.get("/suggest", response_model=list[SearchResult])
async def search_suggestions(
    query: str = Query(..., min_length=1),
    limit: int = Query(default=5, ge=1, le=20),
):
    """Get search suggestions as user types (autocomplete)."""
    try:
        session = await get_neo4j_session()
        async with session:
            results = []
            search_term = query.lower()

            # Get entity suggestions
            result = await session.run(
                """
                MATCH (e:Entity)
                WHERE toLower(e.name) STARTS WITH $search_term
                   OR toLower(e.name) CONTAINS $search_term
                RETURN e.id as id, e.name as name, e.type as type
                ORDER BY
                    CASE WHEN toLower(e.name) STARTS WITH $search_term THEN 0 ELSE 1 END,
                    e.name
                LIMIT $result_limit
                """,
                search_term=search_term,
                result_limit=limit,
            )

            async for record in result:
                results.append(
                    SearchResult(
                        type="entity",
                        id=record["id"],
                        label=record["name"],
                        score=1.0,
                        data={"type": record["type"]},
                    )
                )

            # Get decision suggestions
            result = await session.run(
                """
                MATCH (d:DecisionTrace)
                WHERE toLower(d.trigger) CONTAINS $search_term
                RETURN d.id as id, d.trigger as trigger
                ORDER BY d.created_at DESC
                LIMIT $result_limit
                """,
                search_term=search_term,
                result_limit=limit,
            )

            async for record in result:
                results.append(
                    SearchResult(
                        type="decision",
                        id=record["id"],
                        label=record["trigger"][:60],
                        score=0.9,
                        data={},
                    )
                )

            return results[:limit]
    except DriverError as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")
    except (ClientError, DatabaseError) as e:
        logger.error(f"Search suggest error: {e}")
        raise HTTPException(status_code=500, detail="Search suggestions failed")
