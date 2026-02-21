"""Agent Context Service — composes existing services for AI agent consumption.

Provides structured context from the knowledge graph for AI agents (Claude Code,
Cursor, etc.) without duplicating business logic. All methods are user-scoped.

Inspired by PACEvolve (Coleman et al., Google DeepMind):
- Context Pollution → focused subgraph queries instead of full dumps
- Mode Collapse → SUPERSEDES/CONTRADICTS chains show what was tried and abandoned
- Weak Collaboration → shared knowledge graph as coordination memory
"""

import hashlib
from typing import Optional

from db.neo4j import get_neo4j_session
from models.schemas import (
    AbandonedPattern,
    AgentCheckResponse,
    AgentContextResponse,
    AgentDecisionSummary,
    AgentEntityContextResponse,
    AgentEntitySummary,
    AgentRememberResponse,
    AgentSummaryResponse,
    DecisionCreate,
    EvolutionChain,
)
from services.decision_analyzer import get_decision_analyzer
from services.embeddings import get_embedding_service
from services.entity_resolver import get_entity_resolver
from services.extractor import get_extractor
from utils.cache import get_cached, invalidate_cache, set_cached
from utils.logging import get_logger
from utils.vectors import cosine_similarity

logger = get_logger(__name__)

# Cache key prefix for agent endpoints
AGENT_CACHE_PREFIX = "cache:agent"


def _user_filter(alias: str = "d") -> str:
    """Return a Cypher WHERE clause fragment for user isolation."""
    return f"({alias}.user_id = $user_id OR {alias}.user_id IS NULL)"


def _approximate_tokens(text: str) -> int:
    """Approximate token count using chars/4 heuristic."""
    return len(text) // 4


def _truncate_to_budget(items: list[dict], max_tokens: int, key_fields: list[str]) -> list[dict]:
    """Truncate a list of items to fit within a token budget.

    Keeps items in order (assumed to be sorted by relevance).
    """
    result = []
    used_tokens = 0
    for item in items:
        item_text = " ".join(str(item.get(f, "")) for f in key_fields)
        item_tokens = _approximate_tokens(item_text)
        if used_tokens + item_tokens > max_tokens:
            break
        result.append(item)
        used_tokens += item_tokens
    return result


class AgentContextService:
    """Composes existing services for agent-facing context delivery."""

    def __init__(self, user_id: str = "anonymous"):
        self.user_id = user_id
        self.embedding_service = get_embedding_service()

    async def get_summary(self, project_filter: Optional[str] = None) -> AgentSummaryResponse:
        """Get high-level architectural overview for agent bootstrapping."""
        # Check cache
        cache_key_extra = project_filter or "all"
        cached = await get_cached("agent_summary", self.user_id, cache_key_extra)
        if cached is not None:
            return AgentSummaryResponse(**cached)

        session = await get_neo4j_session()
        async with session:
            # Build project filter clause
            project_clause = ""
            params: dict = {"user_id": self.user_id}
            if project_filter:
                project_clause = "AND d.project_name = $project"
                params["project"] = project_filter

            # Total counts
            result = await session.run(
                f"""
                MATCH (d:DecisionTrace)
                WHERE {_user_filter('d')} {project_clause}
                WITH count(d) AS total_decisions
                OPTIONAL MATCH (d2:DecisionTrace)-[:INVOLVES]->(e:Entity)
                WHERE {_user_filter('d2')} {project_clause.replace('d.', 'd2.')}
                RETURN total_decisions, count(DISTINCT e) AS total_entities
                """,
                **params,
            )
            counts = await result.single()
            total_decisions = counts["total_decisions"] if counts else 0
            total_entities = counts["total_entities"] if counts else 0

            # Top entities by decision count
            result = await session.run(
                f"""
                MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
                WHERE {_user_filter('d')} {project_clause}
                WITH e, count(DISTINCT d) AS dec_count
                ORDER BY dec_count DESC
                LIMIT 15
                OPTIONAL MATCH (e)-[:RELATED_TO|IS_A|PART_OF|DEPENDS_ON|ALTERNATIVE_TO]-(related:Entity)
                RETURN e.name AS name, e.type AS type, dec_count,
                       collect(DISTINCT related.name)[..5] AS related_names
                """,
                **params,
            )
            top_entities = []
            async for r in result:
                top_entities.append(AgentEntitySummary(
                    name=r["name"],
                    type=r["type"],
                    decision_count=r["dec_count"],
                    related_entities=[n for n in r["related_names"] if n],
                ))

            # Top decisions by composite score (confidence + connections + recency)
            result = await session.run(
                f"""
                MATCH (d:DecisionTrace)
                WHERE {_user_filter('d')} {project_clause}
                OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
                OPTIONAL MATCH (superseder:DecisionTrace)-[:SUPERSEDES]->(d)
                WITH d, count(DISTINCT e) AS entity_count,
                     superseder IS NOT NULL AS is_superseded,
                     collect(DISTINCT e.name) AS entity_names
                WITH d, entity_count, is_superseded, entity_names,
                     (COALESCE(d.confidence, 0.5) * 0.4 +
                      toFloat(entity_count) / 10.0 * 0.3 +
                      CASE WHEN d.created_at IS NOT NULL THEN 0.3 ELSE 0.0 END) AS composite_score
                ORDER BY composite_score DESC
                LIMIT 10
                RETURN d.id AS id, d.trigger AS trigger,
                       COALESCE(d.agent_decision, d.decision) AS decision,
                       COALESCE(d.agent_rationale, d.rationale) AS rationale,
                       COALESCE(d.confidence, 0.5) AS confidence,
                       d.created_at AS created_at, d.source AS source,
                       NOT is_superseded AS is_current, entity_names
                """,
                **params,
            )
            top_decisions = []
            async for r in result:
                top_decisions.append(AgentDecisionSummary(
                    id=r["id"],
                    trigger=r["trigger"] or "",
                    decision=r["decision"] or "",
                    rationale=r["rationale"] or "",
                    confidence=r["confidence"],
                    created_at=r["created_at"],
                    source=r["source"],
                    is_current=r["is_current"],
                    entities=[n for n in r["entity_names"] if n],
                ))

            # Unresolved contradictions (CONTRADICTS where neither side is superseded)
            result = await session.run(
                f"""
                MATCH (d1:DecisionTrace)-[c:CONTRADICTS]-(d2:DecisionTrace)
                WHERE {_user_filter('d1')} AND {_user_filter('d2')}
                AND NOT EXISTS {{
                    MATCH (s:DecisionTrace)-[:SUPERSEDES]->(d1)
                }}
                AND NOT EXISTS {{
                    MATCH (s:DecisionTrace)-[:SUPERSEDES]->(d2)
                }}
                RETURN d1.id AS id1, d1.trigger AS trigger1,
                       COALESCE(d1.agent_decision, d1.decision) AS decision1,
                       d2.id AS id2, d2.trigger AS trigger2,
                       COALESCE(d2.agent_decision, d2.decision) AS decision2,
                       c.confidence AS confidence, c.reasoning AS reasoning
                LIMIT 10
                """,
                user_id=self.user_id,
            )
            contradictions = []
            seen_pairs = set()
            async for r in result:
                pair = tuple(sorted([r["id1"], r["id2"]]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                contradictions.append({
                    "decision_a": {"id": r["id1"], "trigger": r["trigger1"] or "", "decision": r["decision1"] or ""},
                    "decision_b": {"id": r["id2"], "trigger": r["trigger2"] or "", "decision": r["decision2"] or ""},
                    "confidence": r["confidence"] or 0.5,
                    "reasoning": r["reasoning"] or "",
                })

            # Knowledge gaps (entity types with few decisions or low avg confidence)
            result = await session.run(
                f"""
                MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
                WHERE {_user_filter('d')}
                WITH e.type AS entity_type, count(DISTINCT d) AS dec_count,
                     avg(COALESCE(d.confidence, 0.5)) AS avg_confidence
                WHERE dec_count <= 2 OR avg_confidence < 0.6
                RETURN entity_type, dec_count, avg_confidence
                ORDER BY dec_count ASC, avg_confidence ASC
                LIMIT 10
                """,
                user_id=self.user_id,
            )
            knowledge_gaps = []
            async for r in result:
                knowledge_gaps.append({
                    "entity_type": r["entity_type"],
                    "decision_count": r["dec_count"],
                    "avg_confidence": round(r["avg_confidence"], 2),
                })

        response = AgentSummaryResponse(
            total_decisions=total_decisions,
            total_entities=total_entities,
            top_technologies=top_entities,
            top_decisions=top_decisions,
            unresolved_contradictions=contradictions,
            knowledge_gaps=knowledge_gaps,
            project_name=project_filter,
        )

        # Cache for 120s
        await set_cached("agent_summary", self.user_id, response.model_dump(), 120, cache_key_extra)
        return response

    async def get_context(
        self,
        query: str,
        max_decisions: int = 10,
        max_tokens: int = 4000,
        include_evolution: bool = True,
        include_entities: bool = True,
        fmt: str = "json",
        project_filter: Optional[str] = None,
    ) -> AgentContextResponse:
        """Focused context query using hybrid search."""
        # Check cache
        query_hash = hashlib.md5(query.encode()).hexdigest()[:12]
        cache_key = f"{query_hash}:{max_decisions}:{project_filter or 'all'}"
        cached = await get_cached("agent_context", self.user_id, cache_key)
        if cached is not None:
            return AgentContextResponse(**cached)

        # Embed query for semantic search
        try:
            query_embedding = await self.embedding_service.embed_text(query, input_type="query")
        except Exception as e:
            logger.warning(f"Embedding failed, falling back to lexical only: {e}")
            query_embedding = None

        session = await get_neo4j_session()
        async with session:
            decisions = []
            entities_map: dict[str, AgentEntitySummary] = {}

            # Build project filter
            project_clause = ""
            params: dict = {"user_id": self.user_id}
            if project_filter:
                project_clause = "AND d.project_name = $project"
                params["project"] = project_filter

            # Hybrid search: lexical + semantic
            decision_scores: dict[str, float] = {}  # id -> combined_score
            decision_data: dict[str, dict] = {}

            # Lexical search via fulltext index
            try:
                result = await session.run(
                    f"""
                    CALL db.index.fulltext.queryNodes('decision_fulltext', $search_text)
                    YIELD node, score AS fulltext_score
                    WHERE {_user_filter('node')} {project_clause.replace('d.', 'node.')}
                    RETURN node.id AS id, node.trigger AS trigger,
                           COALESCE(node.agent_decision, node.decision) AS decision,
                           COALESCE(node.agent_rationale, node.rationale) AS rationale,
                           COALESCE(node.confidence, 0.5) AS confidence,
                           node.created_at AS created_at, node.source AS source,
                           node.embedding AS embedding,
                           fulltext_score
                    ORDER BY fulltext_score DESC
                    LIMIT $limit
                    """,
                    search_text=query,
                    limit=max_decisions * 3,
                    **params,
                )
                async for r in result:
                    normalized = min(r["fulltext_score"] / 10.0, 1.0)
                    decision_scores[r["id"]] = normalized * 0.3  # lexical weight
                    decision_data[r["id"]] = dict(r)
            except Exception as e:
                logger.debug(f"Fulltext search failed: {e}")

            # Semantic search
            if query_embedding:
                try:
                    result = await session.run(
                        f"""
                        CALL db.index.vector.queryNodes('decision_embedding', $top_k, $embedding)
                        YIELD node, score
                        WHERE {_user_filter('node')} {project_clause.replace('d.', 'node.')}
                        RETURN node.id AS id, node.trigger AS trigger,
                               COALESCE(node.agent_decision, node.decision) AS decision,
                               COALESCE(node.agent_rationale, node.rationale) AS rationale,
                               COALESCE(node.confidence, 0.5) AS confidence,
                               node.created_at AS created_at, node.source AS source,
                               score AS semantic_score
                        """,
                        embedding=query_embedding,
                        top_k=max_decisions * 3,
                        **params,
                    )
                    async for r in result:
                        semantic_score = r["semantic_score"] * 0.7  # semantic weight
                        decision_scores[r["id"]] = decision_scores.get(r["id"], 0.0) + semantic_score
                        if r["id"] not in decision_data:
                            decision_data[r["id"]] = dict(r)
                except Exception as e:
                    logger.debug(f"Vector search failed, using manual fallback: {e}")
                    # Manual fallback
                    result = await session.run(
                        f"""
                        MATCH (d:DecisionTrace)
                        WHERE d.embedding IS NOT NULL AND {_user_filter('d')} {project_clause}
                        RETURN d.id AS id, d.trigger AS trigger,
                               COALESCE(d.agent_decision, d.decision) AS decision,
                               COALESCE(d.agent_rationale, d.rationale) AS rationale,
                               COALESCE(d.confidence, 0.5) AS confidence,
                               d.created_at AS created_at, d.source AS source,
                               d.embedding AS embedding
                        """,
                        **params,
                    )
                    async for r in result:
                        sim = cosine_similarity(query_embedding, r["embedding"])
                        if sim > 0.3:
                            semantic_score = sim * 0.7
                            decision_scores[r["id"]] = decision_scores.get(r["id"], 0.0) + semantic_score
                            if r["id"] not in decision_data:
                                decision_data[r["id"]] = dict(r)

            # Sort by combined score and take top N
            sorted_ids = sorted(decision_scores.keys(), key=lambda x: decision_scores[x], reverse=True)
            top_ids = sorted_ids[:max_decisions]

            # Check supersession status for top results
            if top_ids:
                result = await session.run(
                    """
                    UNWIND $ids AS did
                    MATCH (d:DecisionTrace {id: did})
                    OPTIONAL MATCH (superseder:DecisionTrace)-[:SUPERSEDES]->(d)
                    OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
                    RETURN d.id AS id, superseder IS NOT NULL AS is_superseded,
                           collect(DISTINCT e.name) AS entity_names
                    """,
                    ids=top_ids,
                )
                supersession_map: dict[str, bool] = {}
                entity_names_map: dict[str, list[str]] = {}
                async for r in result:
                    supersession_map[r["id"]] = r["is_superseded"]
                    entity_names_map[r["id"]] = [n for n in r["entity_names"] if n]

                for did in top_ids:
                    data = decision_data.get(did)
                    if not data:
                        continue
                    decisions.append(AgentDecisionSummary(
                        id=did,
                        trigger=data.get("trigger") or "",
                        decision=data.get("decision") or "",
                        rationale=data.get("rationale") or "",
                        confidence=data.get("confidence", 0.5),
                        created_at=data.get("created_at"),
                        source=data.get("source"),
                        relevance_score=round(decision_scores.get(did, 0.0), 3),
                        is_current=not supersession_map.get(did, False),
                        entities=entity_names_map.get(did, []),
                    ))

            # Token budget enforcement
            decisions = _truncate_to_budget(
                [d.model_dump() for d in decisions],
                max_tokens,
                ["trigger", "decision", "rationale"],
            )
            decisions = [AgentDecisionSummary(**d) for d in decisions]

            # Get entities for matched decisions
            if include_entities and top_ids:
                result = await session.run(
                    """
                    MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
                    WHERE d.id IN $ids
                    WITH e, count(DISTINCT d) AS dec_count
                    OPTIONAL MATCH (e)-[:RELATED_TO|IS_A|PART_OF|DEPENDS_ON]-(related:Entity)
                    RETURN DISTINCT e.name AS name, e.type AS type, dec_count,
                           collect(DISTINCT related.name)[..5] AS related_names
                    ORDER BY dec_count DESC
                    LIMIT 30
                    """,
                    ids=top_ids,
                )
                async for r in result:
                    entities_map[r["name"]] = AgentEntitySummary(
                        name=r["name"],
                        type=r["type"],
                        decision_count=r["dec_count"],
                        related_entities=[n for n in r["related_names"] if n],
                    )

            # Evolution chains
            evolution_chains: list[EvolutionChain] = []
            if include_evolution and top_ids:
                # SUPERSEDES chains involving our decisions
                result = await session.run(
                    f"""
                    MATCH path = (newer:DecisionTrace)-[:SUPERSEDES*1..3]->(older:DecisionTrace)
                    WHERE (newer.id IN $ids OR older.id IN $ids)
                    AND {_user_filter('newer')} AND {_user_filter('older')}
                    UNWIND nodes(path) AS n
                    WITH path, collect(DISTINCT {{
                        id: n.id,
                        trigger: n.trigger,
                        decision: COALESCE(n.agent_decision, n.decision),
                        rationale: COALESCE(n.agent_rationale, n.rationale),
                        confidence: COALESCE(n.confidence, 0.5),
                        created_at: n.created_at
                    }}) AS chain_nodes
                    RETURN chain_nodes
                    LIMIT 5
                    """,
                    ids=top_ids,
                    user_id=self.user_id,
                )
                async for r in result:
                    chain_decisions = [
                        AgentDecisionSummary(
                            id=n["id"],
                            trigger=n["trigger"] or "",
                            decision=n["decision"] or "",
                            rationale=n["rationale"] or "",
                            confidence=n["confidence"],
                            created_at=n["created_at"],
                        )
                        for n in r["chain_nodes"] if n.get("id")
                    ]
                    if chain_decisions:
                        evolution_chains.append(EvolutionChain(
                            chain_type="supersedes",
                            decisions=chain_decisions,
                        ))

                # CONTRADICTS involving our decisions
                result = await session.run(
                    f"""
                    MATCH (d1:DecisionTrace)-[c:CONTRADICTS]-(d2:DecisionTrace)
                    WHERE (d1.id IN $ids OR d2.id IN $ids)
                    AND {_user_filter('d1')} AND {_user_filter('d2')}
                    RETURN d1.id AS id1, d1.trigger AS trigger1,
                           COALESCE(d1.agent_decision, d1.decision) AS decision1,
                           d2.id AS id2, d2.trigger AS trigger2,
                           COALESCE(d2.agent_decision, d2.decision) AS decision2,
                           c.reasoning AS reasoning
                    LIMIT 5
                    """,
                    ids=top_ids,
                    user_id=self.user_id,
                )
                async for r in result:
                    evolution_chains.append(EvolutionChain(
                        chain_type="contradicts",
                        decisions=[
                            AgentDecisionSummary(
                                id=r["id1"], trigger=r["trigger1"] or "",
                                decision=r["decision1"] or "", rationale="", confidence=0.5,
                            ),
                            AgentDecisionSummary(
                                id=r["id2"], trigger=r["trigger2"] or "",
                                decision=r["decision2"] or "", rationale="", confidence=0.5,
                            ),
                        ],
                        reasoning=r["reasoning"],
                    ))

        # Build markdown if requested
        markdown = None
        if fmt == "markdown":
            markdown = self._render_context_markdown(query, decisions, list(entities_map.values()), evolution_chains)

        response = AgentContextResponse(
            query=query,
            decisions=decisions,
            entities=list(entities_map.values()),
            evolution_chains=evolution_chains,
            total_decisions_searched=len(decision_data),
            markdown=markdown,
        )

        # Cache for 30s
        await set_cached("agent_context", self.user_id, response.model_dump(), 30, cache_key)
        return response

    async def get_entity_context(self, entity_name: str) -> AgentEntityContextResponse:
        """Get everything about a specific entity."""
        # Check cache
        cache_key = entity_name.lower()
        cached_val = await get_cached("agent_entity", self.user_id, cache_key)
        if cached_val is not None:
            return AgentEntityContextResponse(**cached_val)

        session = await get_neo4j_session()
        async with session:
            # Resolve entity name (handles aliases, canonical names)
            resolver = get_entity_resolver(session, user_id=self.user_id)
            resolved = await resolver.resolve(entity_name, "concept")

            # Get entity details
            result = await session.run(
                """
                MATCH (e:Entity {id: $entity_id})
                RETURN e.name AS name, e.type AS type,
                       COALESCE(e.aliases, []) AS aliases
                """,
                entity_id=resolved.id,
            )
            entity_record = await result.single()
            if not entity_record:
                # Entity not found — return empty response
                return AgentEntityContextResponse(
                    name=entity_name, type="unknown", decisions=[], timeline=[],
                )

            # Get all decisions involving this entity
            result = await session.run(
                f"""
                MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity {{id: $entity_id}})
                WHERE {_user_filter('d')}
                OPTIONAL MATCH (superseder:DecisionTrace)-[:SUPERSEDES]->(d)
                OPTIONAL MATCH (d)-[:INVOLVES]->(other_e:Entity)
                WHERE other_e.id <> $entity_id
                RETURN d.id AS id, d.trigger AS trigger,
                       COALESCE(d.agent_decision, d.decision) AS decision,
                       COALESCE(d.agent_rationale, d.rationale) AS rationale,
                       COALESCE(d.confidence, 0.5) AS confidence,
                       d.created_at AS created_at, d.source AS source,
                       superseder IS NOT NULL AS is_superseded,
                       collect(DISTINCT other_e.name) AS other_entities
                ORDER BY d.created_at DESC
                """,
                entity_id=resolved.id,
                user_id=self.user_id,
            )
            decisions = []
            async for r in result:
                decisions.append(AgentDecisionSummary(
                    id=r["id"],
                    trigger=r["trigger"] or "",
                    decision=r["decision"] or "",
                    rationale=r["rationale"] or "",
                    confidence=r["confidence"],
                    created_at=r["created_at"],
                    source=r["source"],
                    is_current=not r["is_superseded"],
                    entities=[n for n in r["other_entities"] if n],
                ))

            # Get related entities
            result = await session.run(
                """
                MATCH (e:Entity {id: $entity_id})-[r]-(related:Entity)
                WHERE type(r) IN ['RELATED_TO', 'IS_A', 'PART_OF', 'DEPENDS_ON', 'ALTERNATIVE_TO']
                OPTIONAL MATCH (d:DecisionTrace)-[:INVOLVES]->(related)
                RETURN DISTINCT related.name AS name, related.type AS type,
                       count(DISTINCT d) AS dec_count, type(r) AS rel_type
                ORDER BY dec_count DESC
                LIMIT 20
                """,
                entity_id=resolved.id,
            )
            related_entities = []
            async for r in result:
                related_entities.append(AgentEntitySummary(
                    name=r["name"],
                    type=r["type"],
                    decision_count=r["dec_count"],
                ))

            # Get timeline via decision analyzer
            analyzer = get_decision_analyzer(session, user_id=self.user_id)
            timeline = await analyzer.get_entity_timeline(entity_name)

            # Determine current status
            current_status = "active"
            if decisions:
                all_superseded = all(not d.is_current for d in decisions)
                if all_superseded:
                    current_status = "superseded"
                elif any(not d.is_current for d in decisions):
                    current_status = "partially_superseded"

        response = AgentEntityContextResponse(
            name=entity_record["name"],
            type=entity_record["type"],
            aliases=entity_record["aliases"],
            decisions=decisions,
            related_entities=related_entities,
            timeline=[
                {
                    "id": t["id"],
                    "trigger": t.get("trigger", ""),
                    "decision": t.get("decision", ""),
                    "created_at": t.get("created_at"),
                    "supersedes": t.get("supersedes", []),
                    "conflicts_with": t.get("conflicts_with", []),
                }
                for t in timeline
            ],
            current_status=current_status,
        )

        # Cache for 60s
        await set_cached("agent_entity", self.user_id, response.model_dump(), 60, cache_key)
        return response

    async def check_prior_art(
        self,
        proposed_decision: str,
        context: str = "",
        entities: Optional[list[str]] = None,
        threshold: float = 0.5,
    ) -> AgentCheckResponse:
        """Check prior art before making a decision. Always fresh (no cache)."""
        search_text = f"{proposed_decision} {context}"

        # Embed proposed decision for similarity search
        try:
            query_embedding = await self.embedding_service.embed_text(search_text, input_type="query")
        except Exception as e:
            logger.warning(f"Embedding failed for prior art check: {e}")
            query_embedding = None

        session = await get_neo4j_session()
        async with session:
            similar_decisions: list[AgentDecisionSummary] = []
            abandoned_patterns: list[AbandonedPattern] = []
            contradiction_decisions: list[AgentDecisionSummary] = []

            # Find similar decisions via vector search
            if query_embedding:
                try:
                    result = await session.run(
                        f"""
                        CALL db.index.vector.queryNodes('decision_embedding', $top_k, $embedding)
                        YIELD node, score
                        WHERE score > $threshold
                        AND {_user_filter('node')}
                        OPTIONAL MATCH (superseder:DecisionTrace)-[:SUPERSEDES]->(node)
                        OPTIONAL MATCH (node)-[:INVOLVES]->(e:Entity)
                        RETURN node.id AS id, node.trigger AS trigger,
                               COALESCE(node.agent_decision, node.decision) AS decision,
                               COALESCE(node.agent_rationale, node.rationale) AS rationale,
                               COALESCE(node.confidence, 0.5) AS confidence,
                               node.created_at AS created_at, node.source AS source,
                               score AS similarity,
                               superseder IS NOT NULL AS is_superseded,
                               collect(DISTINCT e.name) AS entity_names
                        ORDER BY score DESC
                        """,
                        embedding=query_embedding,
                        top_k=20,
                        threshold=threshold,
                        user_id=self.user_id,
                    )
                    async for r in result:
                        summary = AgentDecisionSummary(
                            id=r["id"],
                            trigger=r["trigger"] or "",
                            decision=r["decision"] or "",
                            rationale=r["rationale"] or "",
                            confidence=r["confidence"],
                            created_at=r["created_at"],
                            source=r["source"],
                            relevance_score=round(r["similarity"], 3),
                            is_current=not r["is_superseded"],
                            entities=[n for n in r["entity_names"] if n],
                        )
                        similar_decisions.append(summary)
                except Exception as e:
                    logger.debug(f"Vector search failed for prior art: {e}")
                    # Manual fallback
                    result = await session.run(
                        f"""
                        MATCH (d:DecisionTrace)
                        WHERE d.embedding IS NOT NULL AND {_user_filter('d')}
                        OPTIONAL MATCH (superseder:DecisionTrace)-[:SUPERSEDES]->(d)
                        OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
                        RETURN d.id AS id, d.trigger AS trigger,
                               COALESCE(d.agent_decision, d.decision) AS decision,
                               COALESCE(d.agent_rationale, d.rationale) AS rationale,
                               COALESCE(d.confidence, 0.5) AS confidence,
                               d.created_at AS created_at, d.source AS source,
                               d.embedding AS embedding,
                               superseder IS NOT NULL AS is_superseded,
                               collect(DISTINCT e.name) AS entity_names
                        """,
                        user_id=self.user_id,
                    )
                    async for r in result:
                        sim = cosine_similarity(query_embedding, r["embedding"])
                        if sim > threshold:
                            similar_decisions.append(AgentDecisionSummary(
                                id=r["id"],
                                trigger=r["trigger"] or "",
                                decision=r["decision"] or "",
                                rationale=r["rationale"] or "",
                                confidence=r["confidence"],
                                created_at=r["created_at"],
                                source=r["source"],
                                relevance_score=round(sim, 3),
                                is_current=not r["is_superseded"],
                                entities=[n for n in r["entity_names"] if n],
                            ))
                    similar_decisions.sort(key=lambda x: x.relevance_score, reverse=True)
                    similar_decisions = similar_decisions[:20]

            # Find abandoned patterns (superseded decisions matching our entities)
            if entities:
                result = await session.run(
                    f"""
                    MATCH (newer:DecisionTrace)-[s:SUPERSEDES]->(older:DecisionTrace)
                    WHERE {_user_filter('newer')} AND {_user_filter('older')}
                    MATCH (older)-[:INVOLVES]->(e:Entity)
                    WHERE toLower(e.name) IN $entity_names
                    RETURN older.id AS old_id, older.trigger AS old_trigger,
                           COALESCE(older.agent_decision, older.decision) AS old_decision,
                           COALESCE(older.agent_rationale, older.rationale) AS old_rationale,
                           COALESCE(older.confidence, 0.5) AS old_confidence,
                           older.created_at AS old_created_at,
                           newer.id AS new_id, newer.trigger AS new_trigger,
                           COALESCE(newer.agent_decision, newer.decision) AS new_decision,
                           COALESCE(newer.agent_rationale, newer.rationale) AS new_rationale,
                           COALESCE(newer.confidence, 0.5) AS new_confidence,
                           newer.created_at AS new_created_at,
                           s.reasoning AS reasoning
                    LIMIT 10
                    """,
                    entity_names=[e.lower() for e in entities],
                    user_id=self.user_id,
                )
                async for r in result:
                    abandoned_patterns.append(AbandonedPattern(
                        original_decision=AgentDecisionSummary(
                            id=r["old_id"], trigger=r["old_trigger"] or "",
                            decision=r["old_decision"] or "", rationale=r["old_rationale"] or "",
                            confidence=r["old_confidence"], created_at=r["old_created_at"],
                            is_current=False,
                        ),
                        superseded_by=AgentDecisionSummary(
                            id=r["new_id"], trigger=r["new_trigger"] or "",
                            decision=r["new_decision"] or "", rationale=r["new_rationale"] or "",
                            confidence=r["new_confidence"], created_at=r["new_created_at"],
                        ),
                        reasoning=r["reasoning"],
                    ))

            # Check for contradictions with existing decisions
            for sim_dec in similar_decisions[:5]:
                result = await session.run(
                    f"""
                    MATCH (d:DecisionTrace {{id: $id}})-[c:CONTRADICTS]-(other:DecisionTrace)
                    WHERE {_user_filter('other')}
                    RETURN other.id AS id, other.trigger AS trigger,
                           COALESCE(other.agent_decision, other.decision) AS decision,
                           COALESCE(other.agent_rationale, other.rationale) AS rationale,
                           COALESCE(other.confidence, 0.5) AS confidence,
                           c.reasoning AS reasoning
                    """,
                    id=sim_dec.id,
                    user_id=self.user_id,
                )
                async for r in result:
                    contradiction_decisions.append(AgentDecisionSummary(
                        id=r["id"],
                        trigger=r["trigger"] or "",
                        decision=r["decision"] or "",
                        rationale=r["rationale"] or "",
                        confidence=r["confidence"],
                    ))

        # Determine recommendation
        if contradiction_decisions:
            recommendation = "resolve_contradiction"
            reason = f"Found {len(contradiction_decisions)} contradicting decision(s). Review before proceeding."
        elif similar_decisions and similar_decisions[0].relevance_score > 0.8:
            recommendation = "review_similar"
            reason = f"Found {len(similar_decisions)} highly similar decision(s). The top match has {similar_decisions[0].relevance_score:.0%} similarity."
        elif abandoned_patterns:
            recommendation = "review_similar"
            reason = f"Found {len(abandoned_patterns)} abandoned pattern(s) related to your entities. Review what was tried before."
        else:
            recommendation = "proceed"
            reason = "No significant prior art found. This appears to be a new decision area."

        return AgentCheckResponse(
            proposed_decision=proposed_decision,
            similar_decisions=similar_decisions[:10],
            abandoned_patterns=abandoned_patterns,
            contradictions=contradiction_decisions,
            recommendation=recommendation,
            recommendation_reason=reason,
        )

    async def remember_decision(
        self,
        trigger: str,
        context: str,
        options: list[str],
        decision: str,
        rationale: str,
        confidence: float = 0.8,
        entities: Optional[list[str]] = None,
        agent_name: str = "unknown-agent",
        project_name: Optional[str] = None,
    ) -> AgentRememberResponse:
        """Record an agent-made decision and return context about it."""
        extractor = get_extractor()

        # Create DecisionCreate object
        decision_create = DecisionCreate(
            trigger=trigger,
            context=context,
            options=options,
            decision=decision,
            rationale=rationale,
            confidence=confidence,
            source=f"agent:{agent_name}",
            project_name=project_name,
        )

        # Save decision using existing extractor
        decision_id = await extractor.save_decision(
            decision=decision_create,
            source=f"agent:{agent_name}",
            user_id=self.user_id,
            project_name=project_name,
        )

        # Get extracted entities
        session = await get_neo4j_session()
        entities_extracted: list[str] = []
        async with session:
            result = await session.run(
                """
                MATCH (d:DecisionTrace {id: $id})-[:INVOLVES]->(e:Entity)
                RETURN e.name AS name
                """,
                id=decision_id,
            )
            async for r in result:
                if r["name"]:
                    entities_extracted.append(r["name"])

            # Find similar existing decisions
            similar_existing: list[AgentDecisionSummary] = []
            result = await session.run(
                f"""
                MATCH (d:DecisionTrace {{id: $id}})-[s:SIMILAR_TO]-(other:DecisionTrace)
                WHERE {_user_filter('other')}
                RETURN other.id AS id, other.trigger AS trigger,
                       COALESCE(other.agent_decision, other.decision) AS decision,
                       COALESCE(other.agent_rationale, other.rationale) AS rationale,
                       COALESCE(other.confidence, 0.5) AS confidence,
                       s.score AS similarity
                ORDER BY s.score DESC
                LIMIT 5
                """,
                id=decision_id,
                user_id=self.user_id,
            )
            async for r in result:
                similar_existing.append(AgentDecisionSummary(
                    id=r["id"],
                    trigger=r["trigger"] or "",
                    decision=r["decision"] or "",
                    rationale=r["rationale"] or "",
                    confidence=r["confidence"],
                    relevance_score=round(r["similarity"] or 0, 3),
                ))

            # Check for potential supersedes/contradicts
            potential_supersedes: list[str] = []
            potential_contradicts: list[str] = []
            result = await session.run(
                f"""
                MATCH (d:DecisionTrace {{id: $id}})-[:SUPERSEDES]->(older:DecisionTrace)
                WHERE {_user_filter('older')}
                RETURN older.id AS id
                """,
                id=decision_id,
                user_id=self.user_id,
            )
            async for r in result:
                potential_supersedes.append(r["id"])

            result = await session.run(
                f"""
                MATCH (d:DecisionTrace {{id: $id}})-[:CONTRADICTS]-(other:DecisionTrace)
                WHERE {_user_filter('other')}
                RETURN other.id AS id
                """,
                id=decision_id,
                user_id=self.user_id,
            )
            async for r in result:
                potential_contradicts.append(r["id"])

        # Invalidate agent caches for this user since we just wrote data
        await invalidate_cache("agent_summary", self.user_id)
        await invalidate_cache("agent_context", self.user_id)
        await invalidate_cache("agent_entity", self.user_id)

        return AgentRememberResponse(
            decision_id=decision_id,
            entities_extracted=entities_extracted,
            similar_existing=similar_existing,
            potential_supersedes=potential_supersedes,
            potential_contradicts=potential_contradicts,
        )

    def _render_context_markdown(
        self,
        query: str,
        decisions: list[AgentDecisionSummary],
        entities: list[AgentEntitySummary],
        chains: list[EvolutionChain],
    ) -> str:
        """Render context response as markdown for LLM consumption."""
        lines = [f"# Context: {query}\n"]

        if decisions:
            lines.append("## Relevant Decisions\n")
            for d in decisions:
                status = "CURRENT" if d.is_current else "SUPERSEDED"
                lines.append(f"### [{status}] {d.trigger}")
                lines.append(f"**Decision:** {d.decision}")
                lines.append(f"**Rationale:** {d.rationale}")
                if d.entities:
                    lines.append(f"**Entities:** {', '.join(d.entities)}")
                lines.append(f"**Confidence:** {d.confidence:.0%} | **Relevance:** {d.relevance_score:.0%}\n")

        if entities:
            lines.append("## Key Entities\n")
            for e in entities:
                related = f" (related: {', '.join(e.related_entities)})" if e.related_entities else ""
                lines.append(f"- **{e.name}** ({e.type}) — {e.decision_count} decisions{related}")
            lines.append("")

        if chains:
            lines.append("## Evolution Chains\n")
            for chain in chains:
                lines.append(f"### {chain.chain_type.upper()}")
                for d in chain.decisions:
                    lines.append(f"- {d.trigger}: {d.decision}")
                if chain.reasoning:
                    lines.append(f"  *Reasoning:* {chain.reasoning}")
                lines.append("")

        return "\n".join(lines)
