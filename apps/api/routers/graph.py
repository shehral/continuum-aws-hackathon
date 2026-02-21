"""Knowledge graph API endpoints with semantic search and validation.

All graph operations are user-isolated. Users can only access nodes
and relationships belonging to their own data.

SD-024: Added Redis caching for expensive stats queries.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j.exceptions import ClientError, DatabaseError, DriverError
from pydantic import BaseModel

from db.neo4j import get_neo4j_session
from models.schemas import (
    GraphData,
    GraphEdge,
    GraphNode,
    HybridSearchRequest,
    HybridSearchResult,
    NeighborNode,
    NeighborsResponse,
    PaginatedGraphData,
    PaginationMeta,
    SemanticSearchRequest,
    SimilarDecision,
)
from routers.auth import get_current_user_id
from services.embeddings import get_embedding_service
from utils.cache import get_cached, invalidate_user_caches, set_cached
from utils.logging import get_logger
from utils.vectors import cosine_similarity

logger = get_logger(__name__)

router = APIRouter()


# Response models for new endpoints
class ValidationIssueResponse(BaseModel):
    type: str
    severity: str
    message: str
    affected_nodes: list[str]
    suggested_action: Optional[str] = None
    details: Optional[dict] = None


class ValidationSummary(BaseModel):
    total_issues: int
    by_severity: dict[str, int]
    by_type: dict[str, int]
    issues: list[ValidationIssueResponse]


class ContradictionResponse(BaseModel):
    id: str
    trigger: str
    decision: str
    created_at: Optional[str] = None
    confidence: float
    reasoning: Optional[str] = None


class TimelineEntry(BaseModel):
    id: str
    trigger: str
    decision: str
    rationale: Optional[str] = None
    created_at: Optional[str] = None
    source: Optional[str] = None
    supersedes: list[str] = []
    conflicts_with: list[str] = []


class AnalyzeRelationshipsResponse(BaseModel):
    status: str
    supersedes_found: int
    contradicts_found: int
    supersedes_created: int
    contradicts_created: int


def _user_filter_clause(alias: str = "d") -> str:
    """Return a Cypher WHERE clause for user isolation.

    Includes backward compatibility for data without user_id.
    """
    return f"({alias}.user_id = $user_id OR {alias}.user_id IS NULL)"


@router.get("", response_model=PaginatedGraphData)
async def get_graph(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(
        100, ge=1, le=500, description="Number of decisions per page"
    ),
    include_similarity: bool = Query(True, description="Include SIMILAR_TO edges"),
    include_temporal: bool = Query(True, description="Include INFLUENCED_BY edges"),
    include_entity_relations: bool = Query(
        True, description="Include entity-to-entity edges"
    ),
    include_contradictions: bool = Query(
        False, description="Include CONTRADICTS edges"
    ),
    include_supersessions: bool = Query(False, description="Include SUPERSEDES edges"),
    source_filter: Optional[str] = Query(
        None, description="Filter by source: claude_logs, interview, manual, unknown"
    ),
    project_filter: Optional[str] = Query(
        None, description="Filter by project name"
    ),
    min_confidence: float = Query(
        0.0, ge=0.0, le=1.0, description="Minimum confidence for relationships"
    ),
    user_id: str = Depends(get_current_user_id),
):
    """Get the user's knowledge graph with pagination support (SD-003).

    Returns decisions in pages with their connected entities.
    For large graphs, use smaller page sizes and lazy load neighbors via
    GET /graph/nodes/{node_id}/neighbors.

    Users can only see their own decisions and related entities.
    """
    try:
        session = await get_neo4j_session()
        async with session:
            nodes = []
            edges = []
            decision_ids = set()  # Track which decisions belong to user

            # Calculate pagination offset
            offset = (page - 1) * page_size

            # Build WHERE clause for filters
            where_clauses = ["(d.user_id = $user_id OR d.user_id IS NULL)"]
            query_params = {"user_id": user_id}

            if source_filter:
                where_clauses.append("(d.source = $source OR (d.source IS NULL AND $source = 'unknown'))")
                query_params["source"] = source_filter

            if project_filter:
                where_clauses.append("d.project_name = $project")
                query_params["project"] = project_filter

            where_clause = " AND ".join(where_clauses)

            # First, get total count of decisions for pagination metadata
            count_query = f"""
                MATCH (d:DecisionTrace)
                WHERE {where_clause}
                RETURN count(d) as total
            """
            count_result = await session.run(count_query, **query_params)

            count_record = await count_result.single()
            total_count = count_record["total"] if count_record else 0
            total_pages = (
                (total_count + page_size - 1) // page_size if total_count > 0 else 0
            )
            has_more = page < total_pages

            # Build decision query with user isolation, pagination, and optional filters
            decision_query = f"""
                MATCH (d:DecisionTrace)
                WHERE {where_clause}
                RETURN d, d.embedding IS NOT NULL AS has_embedding
                ORDER BY d.created_at DESC
                SKIP $offset
                LIMIT $limit
            """
            query_params["offset"] = offset
            query_params["limit"] = page_size
            result = await session.run(decision_query, **query_params)

            async for record in result:
                d = record["d"]
                has_embedding = record["has_embedding"]
                decision_ids.add(d["id"])
                nodes.append(
                    GraphNode(
                        id=d["id"],
                        type="decision",
                        label=d.get("trigger", "Decision")[:50],
                        has_embedding=has_embedding,
                        data={
                            "trigger": d.get("trigger", ""),
                            "context": d.get("context", ""),
                            "options": d.get("options", []),
                            "decision": d.get("decision", ""),
                            "rationale": d.get("rationale", ""),
                            "confidence": d.get("confidence", 0.0),
                            "created_at": d.get("created_at", ""),
                            "source": d.get("source", "unknown"),
                        },
                    )
                )

            # Get entities connected to the paginated decisions only
            if decision_ids:
                decision_ids_list = list(decision_ids)
                result = await session.run(
                    """
                    MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
                    WHERE d.id IN $decision_ids
                    WITH DISTINCT e
                    RETURN e, e.embedding IS NOT NULL AS has_embedding
                    """,
                    decision_ids=decision_ids_list,
                )

                entity_ids = set()
                async for record in result:
                    e = record["e"]
                    has_embedding = record["has_embedding"]
                    entity_ids.add(e["id"])
                    nodes.append(
                        GraphNode(
                            id=e["id"],
                            type="entity",
                            label=e.get("name", "Entity"),
                            has_embedding=has_embedding,
                            data={
                                "name": e.get("name", ""),
                                "type": e.get("type", "concept"),
                                "aliases": e.get("aliases", []),
                            },
                        )
                    )

                # Build relationship query based on flags
                rel_types = ["INVOLVES"]
                if include_similarity:
                    rel_types.append("SIMILAR_TO")
                if include_temporal:
                    rel_types.append("INFLUENCED_BY")
                if include_entity_relations:
                    rel_types.extend(
                        [
                            "IS_A",
                            "PART_OF",
                            "RELATED_TO",
                            "DEPENDS_ON",
                            "ALTERNATIVE_TO",
                        ]
                    )
                if include_contradictions:
                    rel_types.append("CONTRADICTS")
                if include_supersessions:
                    rel_types.append("SUPERSEDES")

                # Get relationships only between the paginated nodes
                # For decision-decision relationships within the page
                # For decision-entity relationships for paginated decisions
                all_node_ids = list(decision_ids | entity_ids)
                result = await session.run(
                    """
                    MATCH (a)-[r]->(b)
                    WHERE a.id IN $node_ids AND b.id IN $node_ids
                    AND type(r) IN $rel_types
                    AND (r.confidence IS NULL OR r.confidence >= $min_confidence)
                    AND (r.score IS NULL OR r.score >= $min_confidence)
                    RETURN a.id as source, b.id as target, type(r) as relationship,
                           r.weight as weight, r.score as score, r.confidence as confidence,
                           r.shared_entities as shared_entities, r.reasoning as reasoning
                    """,
                    node_ids=all_node_ids,
                    rel_types=rel_types,
                    min_confidence=min_confidence,
                )

                edge_id = 0
                async for record in result:
                    # Determine edge weight from various properties
                    weight = (
                        record.get("weight")
                        or record.get("score")
                        or record.get("confidence")
                        or 1.0
                    )
                    # Clamp to [0, 1] to handle floating point precision
                    weight = max(0.0, min(1.0, weight))

                    edges.append(
                        GraphEdge(
                            id=f"edge-{edge_id}",
                            source=record["source"],
                            target=record["target"],
                            relationship=record["relationship"],
                            weight=weight,
                        )
                    )
                    edge_id += 1

            # Build pagination metadata
            pagination = PaginationMeta(
                page=page,
                page_size=page_size,
                total_count=total_count,
                total_pages=total_pages,
                has_more=has_more,
            )

            return PaginatedGraphData(nodes=nodes, edges=edges, pagination=pagination)
    except DriverError as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")
    except (ClientError, DatabaseError) as e:
        logger.error(f"Error fetching graph: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch graph data")


@router.get("/all", response_model=GraphData)
async def get_full_graph(
    include_similarity: bool = Query(True, description="Include SIMILAR_TO edges"),
    include_temporal: bool = Query(True, description="Include INFLUENCED_BY edges"),
    include_entity_relations: bool = Query(
        True, description="Include entity-to-entity edges"
    ),
    include_contradictions: bool = Query(
        False, description="Include CONTRADICTS edges"
    ),
    include_supersessions: bool = Query(False, description="Include SUPERSEDES edges"),
    source_filter: Optional[str] = Query(
        None, description="Filter by source: claude_logs, interview, manual, unknown"
    ),
    project_filter: Optional[str] = Query(
        None, description="Filter by project name"
    ),
    min_confidence: float = Query(
        0.0, ge=0.0, le=1.0, description="Minimum confidence for relationships"
    ),
    user_id: str = Depends(get_current_user_id),
):
    """Get the user's complete knowledge graph without pagination.

    WARNING: For large graphs (1000+ decisions), this may be slow.
    Consider using the paginated GET /graph endpoint instead.

    Users can only see their own decisions and related entities.
    """
    try:
        session = await get_neo4j_session()
        async with session:
            nodes = []
            edges = []
            decision_ids = set()  # Track which decisions belong to user

            # Build WHERE clause for filters
            where_clauses = ["(d.user_id = $user_id OR d.user_id IS NULL)"]
            query_params = {"user_id": user_id}

            if source_filter:
                where_clauses.append("(d.source = $source OR (d.source IS NULL AND $source = 'unknown'))")
                query_params["source"] = source_filter

            if project_filter:
                where_clauses.append("d.project_name = $project")
                query_params["project"] = project_filter

            where_clause = " AND ".join(where_clauses)

            # Build decision query with user isolation and optional filters
            decision_query = f"""
                MATCH (d:DecisionTrace)
                WHERE {where_clause}
                RETURN d, d.embedding IS NOT NULL AS has_embedding
            """
            result = await session.run(decision_query, **query_params)

            async for record in result:
                d = record["d"]
                has_embedding = record["has_embedding"]
                decision_ids.add(d["id"])
                nodes.append(
                    GraphNode(
                        id=d["id"],
                        type="decision",
                        label=d.get("trigger", "Decision")[:50],
                        has_embedding=has_embedding,
                        data={
                            "trigger": d.get("trigger", ""),
                            "context": d.get("context", ""),
                            "options": d.get("options", []),
                            "decision": d.get("decision", ""),
                            "rationale": d.get("rationale", ""),
                            "confidence": d.get("confidence", 0.0),
                            "created_at": d.get("created_at", ""),
                            "source": d.get("source", "unknown"),
                        },
                    )
                )

            # Get entities connected to user's decisions only
            result = await session.run(
                """
                MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
                WHERE d.user_id = $user_id OR d.user_id IS NULL
                WITH DISTINCT e
                RETURN e, e.embedding IS NOT NULL AS has_embedding
                """,
                user_id=user_id,
            )

            entity_ids = set()
            async for record in result:
                e = record["e"]
                has_embedding = record["has_embedding"]
                entity_ids.add(e["id"])
                nodes.append(
                    GraphNode(
                        id=e["id"],
                        type="entity",
                        label=e.get("name", "Entity"),
                        has_embedding=has_embedding,
                        data={
                            "name": e.get("name", ""),
                            "type": e.get("type", "concept"),
                            "aliases": e.get("aliases", []),
                        },
                    )
                )

            # Build relationship query based on flags
            rel_types = ["INVOLVES"]
            if include_similarity:
                rel_types.append("SIMILAR_TO")
            if include_temporal:
                rel_types.append("INFLUENCED_BY")
            if include_entity_relations:
                rel_types.extend(
                    ["IS_A", "PART_OF", "RELATED_TO", "DEPENDS_ON", "ALTERNATIVE_TO"]
                )
            if include_contradictions:
                rel_types.append("CONTRADICTS")
            if include_supersessions:
                rel_types.append("SUPERSEDES")

            # Get relationships only between user's nodes
            # For decision-decision relationships, both must belong to user
            # For decision-entity relationships, the decision must belong to user
            result = await session.run(
                """
                MATCH (a)-[r]->(b)
                WHERE (a:DecisionTrace OR a:Entity) AND (b:DecisionTrace OR b:Entity)
                AND type(r) IN $rel_types
                AND (r.confidence IS NULL OR r.confidence >= $min_confidence)
                AND (r.score IS NULL OR r.score >= $min_confidence)
                // User isolation: at least one endpoint must be user's decision
                AND (
                    (a:DecisionTrace AND (a.user_id = $user_id OR a.user_id IS NULL))
                    OR (b:DecisionTrace AND (b.user_id = $user_id OR b.user_id IS NULL))
                    OR (a:Entity AND b:Entity)
                )
                // For entity-entity edges, ensure both entities connect to user's decisions
                WITH a, b, r
                WHERE NOT (a:Entity AND b:Entity)
                   OR EXISTS {
                       MATCH (d:DecisionTrace)-[:INVOLVES]->(a)
                       WHERE d.user_id = $user_id OR d.user_id IS NULL
                   }
                RETURN a.id as source, b.id as target, type(r) as relationship,
                       r.weight as weight, r.score as score, r.confidence as confidence,
                       r.shared_entities as shared_entities, r.reasoning as reasoning
                """,
                rel_types=rel_types,
                min_confidence=min_confidence,
                user_id=user_id,
            )

            edge_id = 0
            async for record in result:
                # Only include edges where both nodes are in user's graph
                source_id = record["source"]
                target_id = record["target"]
                if source_id not in decision_ids and source_id not in entity_ids:
                    continue
                if target_id not in decision_ids and target_id not in entity_ids:
                    continue

                # Determine edge weight from various properties
                weight = (
                    record.get("weight")
                    or record.get("score")
                    or record.get("confidence")
                    or 1.0
                )
                # Clamp to [0, 1] to handle floating point precision
                weight = max(0.0, min(1.0, weight))

                edges.append(
                    GraphEdge(
                        id=f"edge-{edge_id}",
                        source=source_id,
                        target=target_id,
                        relationship=record["relationship"],
                        weight=weight,
                    )
                )
                edge_id += 1

            return GraphData(nodes=nodes, edges=edges)
    except DriverError as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")
    except (ClientError, DatabaseError) as e:
        logger.error(f"Error fetching graph: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch graph data")


@router.get("/nodes/{node_id}/neighbors", response_model=NeighborsResponse)
async def get_node_neighbors(
    node_id: str,
    limit: int = Query(
        50, ge=1, le=200, description="Maximum number of neighbors to return"
    ),
    relationship_types: Optional[str] = Query(
        None,
        description="Comma-separated list of relationship types to include (e.g., 'INVOLVES,SIMILAR_TO')",
    ),
    user_id: str = Depends(get_current_user_id),
):
    """Get neighbors of a specific node for lazy loading (SD-003).

    Returns nodes directly connected to the specified node along with
    relationship information. Useful for expanding the graph on-demand
    when a user clicks on a node.

    Users can only access their own data.
    """
    try:
        session = await get_neo4j_session()
        async with session:
            neighbors = []

            # Parse relationship types if provided
            rel_type_filter = ""
            rel_types_list = None
            if relationship_types:
                rel_types_list = [
                    rt.strip().upper() for rt in relationship_types.split(",")
                ]
                rel_type_filter = "AND type(r) IN $rel_types"

            # Verify the node exists and belongs to user
            # Check if it's a decision
            verify_result = await session.run(
                """
                MATCH (n)
                WHERE n.id = $node_id
                AND (
                    (n:DecisionTrace AND (n.user_id = $user_id OR n.user_id IS NULL))
                    OR (n:Entity AND EXISTS {
                        MATCH (d:DecisionTrace)-[:INVOLVES]->(n)
                        WHERE d.user_id = $user_id OR d.user_id IS NULL
                    })
                )
                RETURN labels(n)[0] as node_type
                """,
                node_id=node_id,
                user_id=user_id,
            )
            verify_record = await verify_result.single()
            if not verify_record:
                raise HTTPException(status_code=404, detail="Node not found")

            # Get outgoing neighbors
            outgoing_query = f"""
                MATCH (source)-[r]->(target)
                WHERE source.id = $node_id
                AND (
                    (target:DecisionTrace AND (target.user_id = $user_id OR target.user_id IS NULL))
                    OR (target:Entity AND EXISTS {{
                        MATCH (d:DecisionTrace)-[:INVOLVES]->(target)
                        WHERE d.user_id = $user_id OR d.user_id IS NULL
                    }})
                )
                {rel_type_filter}
                RETURN target, type(r) as relationship,
                       r.weight as weight, r.score as score, r.confidence as confidence,
                       labels(target)[0] as target_type,
                       target.embedding IS NOT NULL as has_embedding
                LIMIT $limit
            """

            params = {"node_id": node_id, "user_id": user_id, "limit": limit}
            if rel_types_list:
                params["rel_types"] = rel_types_list

            result = await session.run(outgoing_query, **params)
            async for record in result:
                target = record["target"]
                target_type = record["target_type"]
                has_embedding = record["has_embedding"]

                # Build node based on type
                if target_type == "DecisionTrace":
                    node = GraphNode(
                        id=target["id"],
                        type="decision",
                        label=target.get("trigger", "Decision")[:50],
                        has_embedding=has_embedding,
                        data={
                            "trigger": target.get("trigger", ""),
                            "context": target.get("context", ""),
                            "options": target.get("options", []),
                            "decision": target.get("decision", ""),
                            "rationale": target.get("rationale", ""),
                            "confidence": target.get("confidence", 0.0),
                            "created_at": target.get("created_at", ""),
                            "source": target.get("source", "unknown"),
                        },
                    )
                else:
                    node = GraphNode(
                        id=target["id"],
                        type="entity",
                        label=target.get("name", "Entity"),
                        has_embedding=has_embedding,
                        data={
                            "name": target.get("name", ""),
                            "type": target.get("type", "concept"),
                            "aliases": target.get("aliases", []),
                        },
                    )

                weight = (
                    record.get("weight")
                    or record.get("score")
                    or record.get("confidence")
                )
                # Clamp to [0, 1] to handle floating point precision
                if weight is not None:
                    weight = max(0.0, min(1.0, weight))

                neighbors.append(
                    NeighborNode(
                        node=node,
                        relationship=record["relationship"],
                        direction="outgoing",
                        weight=weight,
                    )
                )

            # Get incoming neighbors
            incoming_query = f"""
                MATCH (source)-[r]->(target)
                WHERE target.id = $node_id
                AND (
                    (source:DecisionTrace AND (source.user_id = $user_id OR source.user_id IS NULL))
                    OR (source:Entity AND EXISTS {{
                        MATCH (d:DecisionTrace)-[:INVOLVES]->(source)
                        WHERE d.user_id = $user_id OR d.user_id IS NULL
                    }})
                )
                {rel_type_filter}
                RETURN source, type(r) as relationship,
                       r.weight as weight, r.score as score, r.confidence as confidence,
                       labels(source)[0] as source_type,
                       source.embedding IS NOT NULL as has_embedding
                LIMIT $limit
            """

            result = await session.run(incoming_query, **params)
            async for record in result:
                source = record["source"]
                source_type = record["source_type"]
                has_embedding = record["has_embedding"]

                # Build node based on type
                if source_type == "DecisionTrace":
                    node = GraphNode(
                        id=source["id"],
                        type="decision",
                        label=source.get("trigger", "Decision")[:50],
                        has_embedding=has_embedding,
                        data={
                            "trigger": source.get("trigger", ""),
                            "context": source.get("context", ""),
                            "options": source.get("options", []),
                            "decision": source.get("decision", ""),
                            "rationale": source.get("rationale", ""),
                            "confidence": source.get("confidence", 0.0),
                            "created_at": source.get("created_at", ""),
                            "source": source.get("source", "unknown"),
                        },
                    )
                else:
                    node = GraphNode(
                        id=source["id"],
                        type="entity",
                        label=source.get("name", "Entity"),
                        has_embedding=has_embedding,
                        data={
                            "name": source.get("name", ""),
                            "type": source.get("type", "concept"),
                            "aliases": source.get("aliases", []),
                        },
                    )

                weight = (
                    record.get("weight")
                    or record.get("score")
                    or record.get("confidence")
                )
                # Clamp to [0, 1] to handle floating point precision
                if weight is not None:
                    weight = max(0.0, min(1.0, weight))

                neighbors.append(
                    NeighborNode(
                        node=node,
                        relationship=record["relationship"],
                        direction="incoming",
                        weight=weight,
                    )
                )

            return NeighborsResponse(
                source_node_id=node_id,
                neighbors=neighbors,
                total_count=len(neighbors),
            )

    except DriverError as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")
    except HTTPException:
        raise
    except (ClientError, DatabaseError) as e:
        logger.error(f"Error fetching neighbors: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch neighbors")


@router.get("/validate", response_model=ValidationSummary)
async def validate_graph(
    user_id: str = Depends(get_current_user_id),
):
    """Run validation checks on the user's knowledge graph.

    Checks for:
    - Circular dependencies in DEPENDS_ON chains
    - Orphan entities with no relationships
    - Low confidence relationships
    - Duplicate entities (via fuzzy matching)
    - Missing embeddings
    - Invalid relationship configurations
    """
    from services.validator import get_graph_validator

    session = await get_neo4j_session()
    async with session:
        validator = get_graph_validator(session, user_id=user_id)
        issues = await validator.validate_all()

        # Convert to response format
        issue_responses = [
            ValidationIssueResponse(
                type=issue.type.value,
                severity=issue.severity.value,
                message=issue.message,
                affected_nodes=issue.affected_nodes,
                suggested_action=issue.suggested_action,
                details=issue.details,
            )
            for issue in issues
        ]

        # Calculate summary
        by_severity = {"error": 0, "warning": 0, "info": 0}
        by_type = {}

        for issue in issues:
            by_severity[issue.severity.value] += 1
            type_key = issue.type.value
            if type_key not in by_type:
                by_type[type_key] = 0
            by_type[type_key] += 1

        return ValidationSummary(
            total_issues=len(issues),
            by_severity=by_severity,
            by_type=by_type,
            issues=issue_responses,
        )


@router.get(
    "/decisions/{decision_id}/contradictions",
    response_model=list[ContradictionResponse],
)
async def get_contradictions(
    decision_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get decisions that contradict this one.

    First checks existing CONTRADICTS relationships, then analyzes
    similar decisions if no existing relationships found.

    Users can only see contradictions within their own decisions.
    """
    from services.decision_analyzer import get_decision_analyzer

    session = await get_neo4j_session()
    async with session:
        # Verify the decision belongs to the user
        result = await session.run(
            """
            MATCH (d:DecisionTrace {id: $id})
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            RETURN d
            """,
            id=decision_id,
            user_id=user_id,
        )
        if not await result.single():
            raise HTTPException(status_code=404, detail="Decision not found")

        analyzer = get_decision_analyzer(session, user_id=user_id)
        contradictions = await analyzer.detect_contradictions_for_decision(decision_id)

        return [
            ContradictionResponse(
                id=c["id"],
                trigger=c.get("trigger", ""),
                decision=c.get("decision", ""),
                created_at=c.get("created_at"),
                confidence=c.get("confidence", 0.5),
                reasoning=c.get("reasoning"),
            )
            for c in contradictions
        ]


@router.get("/entities/timeline/{entity_name}", response_model=list[TimelineEntry])
async def get_entity_timeline(
    entity_name: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get chronological decisions about an entity for the current user.

    Returns all decisions that involve the specified entity,
    ordered by creation date, with information about supersessions
    and contradictions.
    """
    from services.decision_analyzer import get_decision_analyzer

    session = await get_neo4j_session()
    async with session:
        analyzer = get_decision_analyzer(session, user_id=user_id)
        timeline = await analyzer.get_entity_timeline(entity_name)

        if not timeline:
            raise HTTPException(
                status_code=404, detail=f"No decisions found for entity: {entity_name}"
            )

        return [
            TimelineEntry(
                id=entry["id"],
                trigger=entry.get("trigger", ""),
                decision=entry.get("decision", ""),
                rationale=entry.get("rationale"),
                created_at=entry.get("created_at"),
                source=entry.get("source"),
                supersedes=entry.get("supersedes", []),
                conflicts_with=entry.get("conflicts_with", []),
            )
            for entry in timeline
        ]


@router.post("/analyze-relationships", response_model=AnalyzeRelationshipsResponse)
async def analyze_relationships(
    user_id: str = Depends(get_current_user_id),
):
    """Trigger batch analysis for SUPERSEDES/CONTRADICTS relationships.

    Analyzes all decision pairs that share entities and creates
    SUPERSEDES and CONTRADICTS relationships where detected.

    Only analyzes the current user's decisions.
    """
    from services.decision_analyzer import get_decision_analyzer

    session = await get_neo4j_session()
    async with session:
        analyzer = get_decision_analyzer(session, user_id=user_id)

        # Analyze all pairs
        analysis = await analyzer.analyze_all_pairs()

        # Save relationships
        save_stats = await analyzer.save_relationships(analysis)

        return AnalyzeRelationshipsResponse(
            status="completed",
            supersedes_found=len(analysis.get("supersedes", [])),
            contradicts_found=len(analysis.get("contradicts", [])),
            supersedes_created=save_stats.get("supersedes_created", 0),
            contradicts_created=save_stats.get("contradicts_created", 0),
        )


@router.get("/decisions/{decision_id}/evolution")
async def get_decision_evolution(
    decision_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get the evolution chain for a decision.

    Returns decisions that influenced this one and decisions it supersedes.
    Users can only see evolution within their own decisions.
    """
    from services.decision_analyzer import get_decision_analyzer

    session = await get_neo4j_session()
    async with session:
        # Verify the decision belongs to the user
        result = await session.run(
            """
            MATCH (d:DecisionTrace {id: $id})
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            RETURN d
            """,
            id=decision_id,
            user_id=user_id,
        )
        if not await result.single():
            raise HTTPException(status_code=404, detail="Decision not found")

        analyzer = get_decision_analyzer(session, user_id=user_id)
        evolution = await analyzer.get_decision_evolution(decision_id)

        if not evolution:
            raise HTTPException(
                status_code=404, detail=f"Decision not found: {decision_id}"
            )

        return evolution


@router.post("/entities/merge-duplicates")
async def merge_duplicate_entities(
    user_id: str = Depends(get_current_user_id),
):
    """Find and merge duplicate entities based on fuzzy matching.

    Uses the entity resolver to find similar entity names and
    merges them, transferring all relationships to the primary entity.

    Only merges entities connected to the current user's decisions.
    """
    from services.entity_resolver import get_entity_resolver

    session = await get_neo4j_session()
    async with session:
        resolver = get_entity_resolver(session, user_id=user_id)
        stats = await resolver.merge_duplicate_entities()

        return {
            "status": "completed",
            "groups_found": stats["groups_found"],
            "entities_merged": stats["entities_merged"],
        }


@router.get("/nodes/{node_id}", response_model=GraphNode)
async def get_node_details(
    node_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get details for a specific node including its connections.

    Users can only access their own decisions and entities connected to them.
    """
    session = await get_neo4j_session()
    async with session:
        # Try to find as decision (with user isolation)
        result = await session.run(
            """
            MATCH (d:DecisionTrace {id: $id})
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
            OPTIONAL MATCH (d)-[:SUPERSEDES]->(superseded:DecisionTrace)
            WHERE superseded.user_id = $user_id OR superseded.user_id IS NULL
            OPTIONAL MATCH (d)-[:CONTRADICTS]-(conflicting:DecisionTrace)
            WHERE conflicting.user_id = $user_id OR conflicting.user_id IS NULL
            RETURN d,
                   collect(DISTINCT e.name) as entities,
                   collect(DISTINCT superseded.id) as supersedes,
                   collect(DISTINCT conflicting.id) as conflicts_with,
                   d.embedding IS NOT NULL AS has_embedding,
                   d.verbatim_decision, d.verbatim_trigger, d.decision_span, d.turn_index
            """,
            id=node_id,
            user_id=user_id,
        )

        record = await result.single()
        if record and record["d"]:
            d = record["d"]
            entities = record["entities"]
            supersedes = [s for s in record["supersedes"] if s]
            conflicts_with = [c for c in record["conflicts_with"] if c]
            has_embedding = record["has_embedding"]
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
            
            return GraphNode(
                id=d["id"],
                type="decision",
                label=d.get("trigger", "Decision")[:50],
                has_embedding=has_embedding,
                data={
                    "trigger": d.get("trigger", ""),
                    "context": d.get("context", ""),
                    "options": d.get("options", []),
                    "decision": d.get("decision", ""),
                    "rationale": d.get("rationale", ""),
                    "confidence": d.get("confidence", 0.0),
                    "created_at": d.get("created_at", ""),
                    "entities": entities,
                    "supersedes": supersedes,
                    "conflicts_with": conflicts_with,
                    "verbatim_quote": verbatim_quote,
                    "verbatim_start_char": verbatim_start_char,
                    "verbatim_end_char": verbatim_end_char,
                    "turn_index": d.get("turn_index"),
                },
            )

        # Try to find as entity (only if connected to user's decisions)
        result = await session.run(
            """
            MATCH (e:Entity {id: $id})
            // Verify entity is connected to user's decisions
            WHERE EXISTS {
                MATCH (d:DecisionTrace)-[:INVOLVES]->(e)
                WHERE d.user_id = $user_id OR d.user_id IS NULL
            }
            OPTIONAL MATCH (d:DecisionTrace)-[:INVOLVES]->(e)
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            OPTIONAL MATCH (e)-[r]->(related:Entity)
            WHERE EXISTS {
                MATCH (d2:DecisionTrace)-[:INVOLVES]->(related)
                WHERE d2.user_id = $user_id OR d2.user_id IS NULL
            }
            RETURN e,
                   collect(DISTINCT d.trigger) as decisions,
                   collect(DISTINCT {name: related.name, rel: type(r)}) as related_entities,
                   e.embedding IS NOT NULL AS has_embedding
            """,
            id=node_id,
            user_id=user_id,
        )

        record = await result.single()
        if record and record["e"]:
            e = record["e"]
            decisions = record["decisions"]
            related_entities = record["related_entities"]
            has_embedding = record["has_embedding"]
            return GraphNode(
                id=e["id"],
                type="entity",
                label=e.get("name", "Entity"),
                has_embedding=has_embedding,
                data={
                    "name": e.get("name", ""),
                    "type": e.get("type", "concept"),
                    "aliases": e.get("aliases", []),
                    "decisions": decisions,
                    "related_entities": related_entities,
                },
            )

        raise HTTPException(status_code=404, detail="Node not found")


@router.get("/nodes/{node_id}/similar", response_model=list[SimilarDecision])
async def get_similar_nodes(
    node_id: str,
    top_k: int = Query(5, ge=1, le=20),
    threshold: float = Query(0.5, ge=0.0, le=1.0),
    user_id: str = Depends(get_current_user_id),
):
    """Find semantically similar decisions using embeddings.

    Only finds similar decisions within the user's own data.
    """
    session = await get_neo4j_session()

    async with session:
        # Get the node's embedding (verify ownership)
        result = await session.run(
            """
            MATCH (d:DecisionTrace {id: $id})
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            RETURN d.embedding as embedding, d.trigger as trigger
            """,
            id=node_id,
            user_id=user_id,
        )

        record = await result.single()
        if not record:
            raise HTTPException(status_code=404, detail="Decision not found")

        embedding = record["embedding"]
        if not embedding:
            raise HTTPException(status_code=400, detail="Decision has no embedding")

        # Find similar decisions within user's data (try GDS first, fall back to manual)
        try:
            result = await session.run(
                """
                MATCH (d:DecisionTrace)
                WHERE d.id <> $id AND d.embedding IS NOT NULL
                AND (d.user_id = $user_id OR d.user_id IS NULL)
                WITH d, gds.similarity.cosine(d.embedding, $embedding) AS similarity
                WHERE similarity > $threshold
                OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
                RETURN d.id as id, d.trigger as trigger,
                       COALESCE(d.agent_decision, d.decision) as decision,
                       similarity, collect(e.name) as shared_entities
                ORDER BY similarity DESC
                LIMIT $top_k
                """,
                id=node_id,
                embedding=embedding,
                threshold=threshold,
                top_k=top_k,
                user_id=user_id,
            )
        except (ClientError, DatabaseError):
            # Fall back to manual similarity calculation (GDS not installed)
            result = await session.run(
                """
                MATCH (d:DecisionTrace)
                WHERE d.id <> $id AND d.embedding IS NOT NULL
                AND (d.user_id = $user_id OR d.user_id IS NULL)
                OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
                RETURN d.id as id, d.trigger as trigger,
                       COALESCE(d.agent_decision, d.decision) as decision,
                       d.embedding as other_embedding, collect(e.name) as shared_entities
                """,
                id=node_id,
                user_id=user_id,
            )

            similar = []
            async for r in result:
                other_embedding = r["other_embedding"]
                similarity = cosine_similarity(embedding, other_embedding)
                if similarity > threshold:
                    similar.append(
                        SimilarDecision(
                            id=r["id"],
                            trigger=r["trigger"] or "",
                            decision=r["decision"] or "",
                            similarity=similarity,
                            shared_entities=r["shared_entities"] or [],
                        )
                    )

            similar.sort(key=lambda x: x.similarity, reverse=True)
            return similar[:top_k]

        similar = []
        async for r in result:
            similar.append(
                SimilarDecision(
                    id=r["id"],
                    trigger=r["trigger"] or "",
                    decision=r["decision"] or "",
                    similarity=r["similarity"],
                    shared_entities=r["shared_entities"] or [],
                )
            )

        return similar


@router.post("/search/hybrid", response_model=list[HybridSearchResult])
async def hybrid_search(
    request: HybridSearchRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Perform hybrid search combining lexical (fulltext) and semantic (vector) search.

    Hybrid search improves recall by combining:
    - Lexical search: Good for exact keyword matches, specific terms
    - Semantic search: Good for conceptual similarity, paraphrases

    The final score is computed as:
    combined_score = alpha * lexical_score + (1 - alpha) * semantic_score

    Default alpha=0.3 weights semantic search higher (70%) since it better
    captures meaning, while lexical helps with specific technical terms.

    Only searches within the user's own data.
    """
    embedding_service = get_embedding_service()

    # Generate embedding for semantic search
    try:
        query_embedding = await embedding_service.embed_text(
            request.query, input_type="query"
        )
    except (TimeoutError, ConnectionError) as e:
        logger.warning(
            f"Embedding service unavailable, falling back to lexical only: {e}"
        )
        query_embedding = None

    session = await get_neo4j_session()
    results = []

    async with session:
        # Collect lexical results
        lexical_results = {}  # id -> (score, type, data, matched_fields)
        expanded_node_ids = set()  # Track nodes found via graph expansion

        if request.search_decisions:
            try:
                # Fulltext search on decisions
                result = await session.run(
                    """
                    CALL db.index.fulltext.queryNodes('decision_fulltext', $search_text)
                    YIELD node, score AS fulltext_score
                    WHERE node.user_id = $user_id OR node.user_id IS NULL
                    RETURN node.id AS id, 'decision' AS type,
                           node.trigger AS trigger, node.decision AS decision,
                           node.context AS context, node.rationale AS rationale,
                           node.created_at AS created_at, node.source AS source,
                           fulltext_score
                    ORDER BY fulltext_score DESC
                    LIMIT $limit
                    """,
                    parameters={
                        "search_text": request.query,
                        "user_id": user_id,
                        "limit": request.top_k * 2,
                    },
                )

                async for r in result:
                    # Normalize fulltext score to 0-1 range (Lucene scores can exceed 1)
                    normalized_score = min(r["fulltext_score"] / 10.0, 1.0)
                    matched_fields = []
                    query_lower = request.query.lower()
                    if r["trigger"] and query_lower in r["trigger"].lower():
                        matched_fields.append("trigger")
                    if r["decision"] and query_lower in r["decision"].lower():
                        matched_fields.append("decision")
                    if r["context"] and query_lower in r["context"].lower():
                        matched_fields.append("context")
                    if r["rationale"] and query_lower in r["rationale"].lower():
                        matched_fields.append("rationale")

                    lexical_results[r["id"]] = {
                        "score": normalized_score,
                        "type": "decision",
                        "label": (r["trigger"] or "Decision")[:50],
                        "data": {
                            "trigger": r["trigger"] or "",
                            "decision": r["decision"] or "",
                            "context": r["context"] or "",
                            "rationale": r["rationale"] or "",
                            "created_at": r["created_at"] or "",
                            "source": r["source"] or "unknown",
                        },
                        "matched_fields": matched_fields,
                    }
            except (ClientError, DatabaseError) as e:
                logger.debug(f"Fulltext search failed (index may not exist): {e}")

        if request.search_entities:
            try:
                # Fulltext search on entities (connected to user's decisions)
                result = await session.run(
                    """
                    CALL db.index.fulltext.queryNodes('entity_fulltext', $search_text)
                    YIELD node, score AS fulltext_score
                    WHERE EXISTS {
                        MATCH (d:DecisionTrace)-[:INVOLVES]->(node)
                        WHERE d.user_id = $user_id OR d.user_id IS NULL
                    }
                    RETURN node.id AS id, 'entity' AS type,
                           node.name AS name, node.type AS entity_type,
                           node.aliases AS aliases,
                           fulltext_score
                    ORDER BY fulltext_score DESC
                    LIMIT $limit
                    """,
                    parameters={
                        "search_text": request.query,
                        "user_id": user_id,
                        "limit": request.top_k * 2,
                    },
                )

                async for r in result:
                    normalized_score = min(r["fulltext_score"] / 10.0, 1.0)
                    lexical_results[r["id"]] = {
                        "score": normalized_score,
                        "type": "entity",
                        "label": r["name"] or "Entity",
                        "data": {
                            "name": r["name"] or "",
                            "type": r["entity_type"] or "concept",
                            "aliases": r["aliases"] or [],
                        },
                        "matched_fields": ["name"],
                    }
            except (ClientError, DatabaseError) as e:
                logger.debug(f"Entity fulltext search failed: {e}")

        # RQ3.6.1: Graph-augmented expansion (if graph_depth > 0)
        if request.graph_depth > 0 and lexical_results:
            # Expand via 1-hop relationships (MENTIONS, RELATES_TO, INVOLVES)
            initial_node_ids = list(lexical_results.keys())
            
            for node_id in initial_node_ids[: request.top_k * 2]:  # Limit expansion candidates
                try:
                    # Find connected nodes via relationships
                    expansion_result = await session.run(
                        """
                        MATCH (n)
                        WHERE n.id = $node_id AND (n.user_id = $user_id OR n.user_id IS NULL)
                        MATCH (n)-[r:INVOLVES|MENTIONS|RELATES_TO|FOLLOWS|PRECEDES*1..$depth]-(connected)
                        WHERE (connected.user_id = $user_id OR connected.user_id IS NULL)
                          AND connected.id <> $node_id
                        RETURN DISTINCT connected.id AS connected_id,
                               connected.trigger AS trigger,
                               connected.decision AS decision,
                               connected.context AS context,
                               connected.rationale AS rationale,
                               labels(connected)[0] AS node_type
                        LIMIT 10
                        """,
                        node_id=node_id,
                        user_id=user_id,
                        depth=request.graph_depth,
                    )
                    
                    async for r in expansion_result:
                        connected_id = r["connected_id"]
                        if connected_id not in lexical_results and connected_id not in expanded_node_ids:
                            expanded_node_ids.add(connected_id)
                            # Add expanded nodes with lower initial score (will be reranked)
                            lexical_results[connected_id] = {
                                "score": lexical_results.get(node_id, {}).get("score", 0.0) * 0.7,  # Penalty for expansion
                                "type": r["node_type"] or "decision",
                                "label": (r["trigger"] or r["decision"] or "Node")[:50],
                                "data": {
                                    "trigger": r["trigger"] or "",
                                    "decision": r["decision"] or "",
                                    "context": r["context"] or "",
                                    "rationale": r["rationale"] or "",
                                },
                                "matched_fields": ["graph_expansion"],
                            }
                except Exception as e:
                    logger.debug(f"Graph expansion failed for node {node_id}: {e}")
        
        # Collect semantic results
        semantic_results = {}  # id -> score

        if query_embedding:
            if request.search_decisions:
                try:
                    # Try vector index first
                    result = await session.run(
                        """
                        CALL db.index.vector.queryNodes('decision_embedding', $top_k, $embedding)
                        YIELD node, score
                        WHERE node.user_id = $user_id OR node.user_id IS NULL
                        RETURN node.id AS id, score AS semantic_score,
                               'decision' AS type,
                               node.trigger AS trigger, node.decision AS decision,
                               node.context AS context, node.rationale AS rationale,
                               node.created_at AS created_at, node.source AS source
                        """,
                        embedding=query_embedding,
                        top_k=request.top_k * 2,
                        user_id=user_id,
                    )

                    async for r in result:
                        semantic_results[r["id"]] = r["semantic_score"]
                        # Add to results if not already from lexical
                        if r["id"] not in lexical_results:
                            lexical_results[r["id"]] = {
                                "score": 0.0,  # No lexical match
                                "type": "decision",
                                "label": (r["trigger"] or "Decision")[:50],
                                "data": {
                                    "trigger": r["trigger"] or "",
                                    "decision": r["decision"] or "",
                                    "context": r["context"] or "",
                                    "rationale": r["rationale"] or "",
                                    "created_at": r["created_at"] or "",
                                    "source": r["source"] or "unknown",
                                },
                                "matched_fields": [],
                            }
                except (ClientError, DatabaseError) as e:
                    # Fall back to manual calculation
                    logger.debug(
                        f"Vector index not available, falling back to manual: {e}"
                    )
                    result = await session.run(
                        """
                        MATCH (d:DecisionTrace)
                        WHERE d.embedding IS NOT NULL
                        AND (d.user_id = $user_id OR d.user_id IS NULL)
                        RETURN d.id AS id, d.embedding AS embedding,
                               d.trigger AS trigger,
                               COALESCE(d.agent_decision, d.decision) AS decision,
                               d.context AS context,
                               COALESCE(d.agent_rationale, d.rationale) AS rationale,
                               d.created_at AS created_at, d.source AS source
                        """,
                        user_id=user_id,
                    )

                    async for r in result:
                        similarity = cosine_similarity(query_embedding, r["embedding"])
                        if similarity > 0.3:  # Minimum threshold for consideration
                            semantic_results[r["id"]] = similarity
                            if r["id"] not in lexical_results:
                                lexical_results[r["id"]] = {
                                    "score": 0.0,
                                    "type": "decision",
                                    "label": (r["trigger"] or "Decision")[:50],
                                    "data": {
                                        "trigger": r["trigger"] or "",
                                        "decision": r["decision"] or "",
                                        "context": r["context"] or "",
                                        "rationale": r["rationale"] or "",
                                        "created_at": r["created_at"] or "",
                                        "source": r["source"] or "unknown",
                                    },
                                    "matched_fields": [],
                                }

            if request.search_entities:
                try:
                    # Try vector index for entities
                    result = await session.run(
                        """
                        CALL db.index.vector.queryNodes('entity_embedding', $top_k, $embedding)
                        YIELD node, score
                        WHERE EXISTS {
                            MATCH (d:DecisionTrace)-[:INVOLVES]->(node)
                            WHERE d.user_id = $user_id OR d.user_id IS NULL
                        }
                        RETURN node.id AS id, score AS semantic_score,
                               'entity' AS type,
                               node.name AS name, node.type AS entity_type,
                               node.aliases AS aliases
                        """,
                        embedding=query_embedding,
                        top_k=request.top_k * 2,
                        user_id=user_id,
                    )

                    async for r in result:
                        semantic_results[r["id"]] = r["semantic_score"]
                        if r["id"] not in lexical_results:
                            lexical_results[r["id"]] = {
                                "score": 0.0,
                                "type": "entity",
                                "label": r["name"] or "Entity",
                                "data": {
                                    "name": r["name"] or "",
                                    "type": r["entity_type"] or "concept",
                                    "aliases": r["aliases"] or [],
                                },
                                "matched_fields": [],
                            }
                except (ClientError, DatabaseError):
                    # Fall back to manual calculation for entities
                    result = await session.run(
                        """
                        MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
                        WHERE (d.user_id = $user_id OR d.user_id IS NULL)
                        AND e.embedding IS NOT NULL
                        RETURN DISTINCT e.id AS id, e.embedding AS embedding,
                               e.name AS name, e.type AS entity_type,
                               e.aliases AS aliases
                        """,
                        user_id=user_id,
                    )

                    async for r in result:
                        similarity = cosine_similarity(query_embedding, r["embedding"])
                        if similarity > 0.3:
                            semantic_results[r["id"]] = similarity
                            if r["id"] not in lexical_results:
                                lexical_results[r["id"]] = {
                                    "score": 0.0,
                                    "type": "entity",
                                    "label": r["name"] or "Entity",
                                    "data": {
                                        "name": r["name"] or "",
                                        "type": r["entity_type"] or "concept",
                                        "aliases": r["aliases"] or [],
                                    },
                                    "matched_fields": [],
                                }

        # Combine scores and create results
        for node_id, data in lexical_results.items():
            lexical_score = data["score"]
            semantic_score = semantic_results.get(node_id, 0.0)

            # Hybrid score formula
            combined_score = (
                request.alpha * lexical_score + (1 - request.alpha) * semantic_score
            )

            # Apply threshold
            if combined_score >= request.threshold:
                results.append(
                    HybridSearchResult(
                        id=node_id,
                        type=data["type"],
                        label=data["label"],
                        lexical_score=lexical_score,
                        semantic_score=semantic_score,
                        combined_score=combined_score,
                        data=data["data"],
                        matched_fields=data["matched_fields"],
                    )
                )

        # Sort by combined score and limit
        results.sort(key=lambda x: x.combined_score, reverse=True)
        
        # RQ1.2: Apply BGE reranking if enabled (CogCanvas method, +7.7pp improvement)
        from config import get_settings
        from services.reranker import get_reranker
        
        settings = get_settings()
        if settings.bge_reranking_enabled and len(results) > 0:
            try:
                reranker = get_reranker()
                # Prepare candidates with text for reranking (top candidates only)
                candidates_with_text = []
                top_candidates = results[: min(len(results), settings.bge_reranking_top_k)]
                
                for r in top_candidates:
                    # Build text representation for reranking
                    text_parts = []
                    if r.data.get("trigger"):
                        text_parts.append(f"Trigger: {r.data['trigger']}")
                    if r.data.get("decision"):
                        text_parts.append(f"Decision: {r.data['decision']}")
                    if r.data.get("rationale"):
                        text_parts.append(f"Rationale: {r.data['rationale']}")
                    if r.data.get("context"):
                        text_parts.append(f"Context: {r.data['context']}")
                    candidate_text = " ".join(text_parts)
                    
                    if candidate_text:  # Only add if we have text
                        candidates_with_text.append((r.id, candidate_text, r.combined_score))
                
                if candidates_with_text:
                    # Rerank candidates
                    reranked = await reranker.rerank_with_texts(
                        query=request.query,
                        candidates=candidates_with_text,
                        top_k=request.top_k,
                    )
                    
                    # Create map of reranked scores
                    reranked_scores = {cid: score for cid, score in reranked}
                    
                    # Update results with reranked scores
                    for r in results:
                        if r.id in reranked_scores:
                            # Use reranked score as new combined_score
                            r.combined_score = reranked_scores[r.id]
                    
                    # Re-sort by reranked scores
                    results.sort(key=lambda x: x.combined_score, reverse=True)
                    logger.debug(f"BGE reranking applied to {len(reranked)} results")
            except Exception as e:
                logger.warning(f"BGE reranking failed, using original scores: {e}")
        
        return results[: request.top_k]


@router.post("/search/semantic", response_model=list[SimilarDecision])
async def semantic_search(
    request: SemanticSearchRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Search for decisions semantically similar to a query.

    Only searches within the user's own decisions.
    """
    embedding_service = get_embedding_service()

    # Generate embedding for the query
    query_embedding = await embedding_service.embed_text(
        request.query, input_type="query"
    )

    session = await get_neo4j_session()
    async with session:
        # Try vector index search first (with user filtering)
        try:
            result = await session.run(
                """
                CALL db.index.vector.queryNodes('decision_embedding', $top_k * 2, $embedding)
                YIELD node, score
                WHERE score > $threshold
                AND (node.user_id = $user_id OR node.user_id IS NULL)
                WITH node, score
                LIMIT $top_k
                OPTIONAL MATCH (node)-[:INVOLVES]->(e:Entity)
                RETURN node.id as id, node.trigger as trigger, node.decision as decision,
                       score as similarity, collect(e.name) as shared_entities
                """,
                embedding=query_embedding,
                top_k=request.top_k,
                threshold=request.threshold,
                user_id=user_id,
            )
        except (ClientError, DatabaseError):
            # Fall back to manual search (vector index not available)
            result = await session.run(
                """
                MATCH (d:DecisionTrace)
                WHERE d.embedding IS NOT NULL
                AND (d.user_id = $user_id OR d.user_id IS NULL)
                OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
                RETURN d.id as id, d.trigger as trigger,
                       COALESCE(d.agent_decision, d.decision) as decision,
                       d.embedding as other_embedding, collect(e.name) as shared_entities
                """,
                user_id=user_id,
            )

            similar = []
            async for r in result:
                other_embedding = r["other_embedding"]
                similarity = cosine_similarity(query_embedding, other_embedding)
                if similarity > request.threshold:
                    similar.append(
                        SimilarDecision(
                            id=r["id"],
                            trigger=r["trigger"] or "",
                            decision=r["decision"] or "",
                            similarity=similarity,
                            shared_entities=r["shared_entities"] or [],
                        )
                    )

            similar.sort(key=lambda x: x.similarity, reverse=True)
            return similar[: request.top_k]

        results = []
        async for r in result:
            results.append(
                SimilarDecision(
                    id=r["id"],
                    trigger=r["trigger"] or "",
                    decision=r["decision"] or "",
                    similarity=r["similarity"],
                    shared_entities=r["shared_entities"] or [],
                )
            )

        return results


@router.get("/stats")
async def get_graph_stats(
    user_id: str = Depends(get_current_user_id),
):
    """Get statistics about the user's knowledge graph.

    SD-024: Results are cached in Redis for 30 seconds.
    """
    # SD-024: Check cache first
    cached = await get_cached("graph_stats", user_id)
    if cached is not None:
        logger.debug(f"Returning cached graph stats for user {user_id}")
        return cached

    session = await get_neo4j_session()
    async with session:
        result = await session.run(
            """
            MATCH (d:DecisionTrace)
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            WITH count(d) as total_decisions,
                 count(CASE WHEN d.embedding IS NOT NULL THEN 1 END) as decisions_with_embeddings

            // Get entities connected to user's decisions
            OPTIONAL MATCH (d2:DecisionTrace)-[:INVOLVES]->(e:Entity)
            WHERE d2.user_id = $user_id OR d2.user_id IS NULL
            WITH total_decisions, decisions_with_embeddings,
                 count(DISTINCT e) as total_entities,
                 count(DISTINCT CASE WHEN e.embedding IS NOT NULL THEN e END) as entities_with_embeddings

            // Count relationships involving user's data
            OPTIONAL MATCH (d3:DecisionTrace)-[r]->()
            WHERE d3.user_id = $user_id OR d3.user_id IS NULL
            RETURN total_decisions, decisions_with_embeddings,
                   total_entities, entities_with_embeddings,
                   count(r) as total_relationships
            """,
            user_id=user_id,
        )

        record = await result.single()
        if record:
            result = {
                "decisions": {
                    "total": record["total_decisions"],
                    "with_embeddings": record["decisions_with_embeddings"],
                },
                "entities": {
                    "total": record["total_entities"],
                    "with_embeddings": record["entities_with_embeddings"],
                },
                "relationships": record["total_relationships"],
            }
        else:
            result = {
                "decisions": {"total": 0, "with_embeddings": 0},
                "entities": {"total": 0, "with_embeddings": 0},
                "relationships": 0,
            }

        # SD-024: Cache the result for 30 seconds
        await set_cached("graph_stats", user_id, result, ttl=30)
        return result


@router.get("/relationships/types")
async def get_relationship_types(
    user_id: str = Depends(get_current_user_id),
):
    """Get all relationship types and their counts for the user's graph."""
    session = await get_neo4j_session()
    async with session:
        result = await session.run(
            """
            MATCH (d:DecisionTrace)-[r]->()
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            RETURN type(r) as relationship_type, count(r) as count
            ORDER BY count DESC
            """,
            user_id=user_id,
        )

        types = {}
        async for record in result:
            types[record["relationship_type"]] = record["count"]

        return types


@router.delete("/reset")
async def reset_graph(
    confirm: bool = Query(False, description="Must be true to confirm deletion"),
    user_id: str = Depends(get_current_user_id),
):
    """Clear the user's data from the knowledge graph.

    WARNING: This permanently deletes all of the user's decisions,
    and orphaned entities. Pass confirm=true to execute.
    """
    if not confirm:
        return {
            "status": "aborted",
            "message": "Pass confirm=true to delete your graph data",
        }

    session = await get_neo4j_session()
    async with session:
        # Delete user's decisions and their relationships
        await session.run(
            """
            MATCH (d:DecisionTrace)
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            DETACH DELETE d
            """,
            user_id=user_id,
        )

        # Clean up orphaned entities (entities with no remaining connections)
        await session.run(
            """
            MATCH (e:Entity)
            WHERE NOT (e)<-[:INVOLVES]-(:DecisionTrace)
            DETACH DELETE e
            """
        )

    # SD-024: Invalidate user's caches after data deletion
    await invalidate_user_caches(user_id)

    return {"status": "completed", "message": "Your graph data has been deleted"}


@router.get("/sources")
async def get_decision_sources(
    user_id: str = Depends(get_current_user_id),
):
    """Get decision counts by source type for the user.

    SD-024: Results are cached in Redis for 60 seconds.
    """
    # SD-024: Check cache first
    cached = await get_cached("graph_sources", user_id)
    if cached is not None:
        logger.debug(f"Returning cached graph sources for user {user_id}")
        return cached

    session = await get_neo4j_session()
    async with session:
        result = await session.run(
            """
            MATCH (d:DecisionTrace)
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            RETURN
                COALESCE(d.source, 'unknown') as source,
                count(d) as count
            ORDER BY count DESC
            """,
            user_id=user_id,
        )

        sources = {}
        async for record in result:
            sources[record["source"]] = record["count"]

        # SD-024: Cache the result for 60 seconds
        await set_cached("graph_sources", user_id, sources, ttl=60)
        return sources


@router.get("/projects")
async def get_decision_projects(
    user_id: str = Depends(get_current_user_id),
):
    """Get decision counts by project for the user.

    Returns project names with decision counts. Cached for 60 seconds.
    """
    # Check cache first
    cached = await get_cached("graph_projects", user_id)
    if cached is not None:
        logger.debug(f"Returning cached graph projects for user {user_id}")
        return cached

    session = await get_neo4j_session()
    async with session:
        result = await session.run(
            """
            MATCH (d:DecisionTrace)
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            RETURN
                COALESCE(d.project_name, 'unassigned') as project,
                count(d) as count
            ORDER BY count DESC
            """,
            user_id=user_id,
        )

        projects = {}
        async for record in result:
            projects[record["project"]] = record["count"]

        # Cache the result for 60 seconds
        await set_cached("graph_projects", user_id, projects, ttl=60)
        return projects


@router.post("/tag-sources")
async def tag_decision_sources(
    user_id: str = Depends(get_current_user_id),
):
    """
    Tag existing decisions with their source based on heuristics.
    Only tags the user's own decisions.
    """
    session = await get_neo4j_session()
    results = {"tagged": 0}

    async with session:
        # Tag user's decisions without source as 'unknown' (legacy)
        result = await session.run(
            """
            MATCH (d:DecisionTrace)
            WHERE (d.user_id = $user_id OR d.user_id IS NULL)
            AND d.source IS NULL
            SET d.source = 'unknown'
            RETURN count(d) as count
            """,
            user_id=user_id,
        )
        record = await result.single()
        results["tagged"] = record["count"] if record else 0

    return {
        "status": "completed",
        "results": results,
    }


@router.post("/enhance")
async def enhance_graph(
    user_id: str = Depends(get_current_user_id),
):
    """
    Backfill embeddings and relationships for existing nodes.
    Only enhances the user's own data.

    This enhances the graph by:
    1. Adding embeddings to decisions without them
    2. Adding embeddings to entities without them
    3. Creating SIMILAR_TO edges between similar decisions
    4. Creating entity-to-entity relationships
    """
    from services.extractor import DecisionExtractor

    embedding_service = get_embedding_service()
    extractor = DecisionExtractor()

    session = await get_neo4j_session()
    results = {
        "decisions_enhanced": 0,
        "entities_enhanced": 0,
        "similarity_edges_created": 0,
        "entity_relationships_created": 0,
    }

    async with session:
        # 1. Add embeddings to user's decisions without them
        result = await session.run(
            """
            MATCH (d:DecisionTrace)
            WHERE d.embedding IS NULL
            AND (d.user_id = $user_id OR d.user_id IS NULL)
            RETURN d.id as id, d.trigger as trigger, d.context as context,
                   COALESCE(d.agent_decision, d.decision) as decision,
                   COALESCE(d.agent_rationale, d.rationale) as rationale,
                   d.options as options
            """,
            user_id=user_id,
        )

        decisions_to_enhance = [r async for r in result]
        logger.info(
            f"Found {len(decisions_to_enhance)} decisions without embeddings for user {user_id}"
        )

        for dec in decisions_to_enhance:
            try:
                decision_dict = {
                    "trigger": dec["trigger"] or "",
                    "context": dec["context"] or "",
                    "options": dec["options"] or [],
                    "decision": dec["decision"] or "",
                    "rationale": dec["rationale"] or "",
                }
                embedding = await embedding_service.embed_decision(decision_dict)

                await session.run(
                    """
                    MATCH (d:DecisionTrace {id: $id})
                    SET d.embedding = $embedding
                    """,
                    id=dec["id"],
                    embedding=embedding,
                )
                results["decisions_enhanced"] += 1
                logger.debug(f"Added embedding to decision {dec['id'][:8]}...")
            except (TimeoutError, ConnectionError) as e:
                logger.warning(f"Failed to enhance decision {dec['id']}: {e}")
            except (ClientError, DatabaseError) as e:
                logger.warning(f"Database error enhancing decision {dec['id']}: {e}")

        # 2. Add embeddings to entities connected to user's decisions
        result = await session.run(
            """
            MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
            WHERE (d.user_id = $user_id OR d.user_id IS NULL)
            AND e.embedding IS NULL
            RETURN DISTINCT e.id as id, e.name as name, e.type as type
            """,
            user_id=user_id,
        )

        entities_to_enhance = [r async for r in result]
        logger.info(
            f"Found {len(entities_to_enhance)} entities without embeddings for user {user_id}"
        )

        for ent in entities_to_enhance:
            try:
                entity_dict = {"name": ent["name"], "type": ent["type"]}
                embedding = await embedding_service.embed_entity(entity_dict)

                await session.run(
                    """
                    MATCH (e:Entity {id: $id})
                    SET e.embedding = $embedding
                    """,
                    id=ent["id"],
                    embedding=embedding,
                )
                results["entities_enhanced"] += 1
            except (TimeoutError, ConnectionError) as e:
                logger.warning(f"Failed to enhance entity {ent['name']}: {e}")
            except (ClientError, DatabaseError) as e:
                logger.warning(f"Database error enhancing entity {ent['name']}: {e}")

        # 3. Create SIMILAR_TO edges between similar user decisions
        result = await session.run(
            """
            MATCH (d:DecisionTrace)
            WHERE d.embedding IS NOT NULL
            AND (d.user_id = $user_id OR d.user_id IS NULL)
            RETURN d.id as id, d.embedding as embedding
            """,
            user_id=user_id,
        )

        decisions_with_embeddings = [r async for r in result]
        logger.info(
            f"Checking similarity between {len(decisions_with_embeddings)} decisions"
        )

        similarity_threshold = 0.75
        for i, d1 in enumerate(decisions_with_embeddings):
            for d2 in decisions_with_embeddings[i + 1 :]:
                similarity = cosine_similarity(d1["embedding"], d2["embedding"])
                if similarity > similarity_threshold:
                    # Create bidirectional SIMILAR_TO edges
                    await session.run(
                        """
                        MATCH (d1:DecisionTrace {id: $id1})
                        MATCH (d2:DecisionTrace {id: $id2})
                        MERGE (d1)-[r:SIMILAR_TO]->(d2)
                        SET r.score = $score
                        """,
                        id1=d1["id"],
                        id2=d2["id"],
                        score=similarity,
                    )
                    results["similarity_edges_created"] += 1
                    logger.debug(f"Created SIMILAR_TO edge (score: {similarity:.3f})")

        # 4. Create entity-to-entity relationships using LLM (for user's entities)
        result = await session.run(
            """
            MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            RETURN DISTINCT e.id as id, e.name as name, e.type as type
            """,
            user_id=user_id,
        )

        all_entities = [r async for r in result]
        logger.info(f"Analyzing relationships between {len(all_entities)} entities")

        if len(all_entities) >= 2:
            from models.schemas import Entity

            entity_objects = [
                Entity(id=e["id"], name=e["name"], type=e["type"]) for e in all_entities
            ]

            # Process in batches to avoid token limits
            batch_size = 15
            for i in range(0, len(entity_objects), batch_size):
                batch = entity_objects[i : i + batch_size]
                if len(batch) < 2:
                    continue

                try:
                    relationships = await extractor.extract_entity_relationships(batch)
                    logger.debug(f"Found {len(relationships)} relationships in batch")

                    for rel in relationships:
                        rel_type = rel.get(
                            "type", rel.get("relationship", "RELATED_TO")
                        )
                        confidence = rel.get("confidence", 0.8)

                        valid_types = [
                            "IS_A",
                            "PART_OF",
                            "RELATED_TO",
                            "DEPENDS_ON",
                            "ALTERNATIVE_TO",
                        ]
                        if rel_type not in valid_types:
                            rel_type = "RELATED_TO"

                        await session.run(
                            f"""
                            MATCH (e1:Entity)
                            WHERE toLower(e1.name) = toLower($from_name)
                            MATCH (e2:Entity)
                            WHERE toLower(e2.name) = toLower($to_name)
                            WHERE e1 <> e2
                            MERGE (e1)-[r:{rel_type}]->(e2)
                            SET r.confidence = $confidence
                            """,
                            from_name=rel.get("from"),
                            to_name=rel.get("to"),
                            confidence=confidence,
                        )
                        results["entity_relationships_created"] += 1
                except (TimeoutError, ConnectionError) as e:
                    logger.error(
                        f"LLM connection error extracting entity relationships: {e}"
                    )
                except (ClientError, DatabaseError) as e:
                    logger.error(f"Database error saving entity relationships: {e}")

        # 5. Create INFLUENCED_BY temporal chains (within user's data)
        await session.run(
            """
            MATCH (d_new:DecisionTrace)
            WHERE d_new.user_id = $user_id OR d_new.user_id IS NULL
            MATCH (d_old:DecisionTrace)-[:INVOLVES]->(e:Entity)<-[:INVOLVES]-(d_new)
            WHERE d_old.id <> d_new.id
            AND d_old.created_at < d_new.created_at
            AND (d_old.user_id = $user_id OR d_old.user_id IS NULL)
            WITH d_new, d_old, count(DISTINCT e) AS shared_count
            WHERE shared_count >= 2
            MERGE (d_new)-[r:INFLUENCED_BY]->(d_old)
            SET r.shared_entities = shared_count
            """,
            user_id=user_id,
        )

    return {
        "status": "completed",
        "results": results,
    }
