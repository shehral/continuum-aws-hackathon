"""Decision analyzer service for detecting SUPERSEDES and CONTRADICTS relationships.

All analysis is user-scoped. Users can only analyze their own decisions.
"""

import itertools
import json
from json import JSONDecodeError
from typing import Optional

from services.llm import get_llm_client
from utils.logging import get_logger

logger = get_logger(__name__)


class DecisionAnalyzer:
    """Analyze decisions for temporal and contradictory relationships.

    All analysis is scoped to the user's decisions only.

    Detects:
    - SUPERSEDES: New decision replaces an older one
    - CONTRADICTS: Decisions conflict with each other
    """

    def __init__(self, neo4j_session, user_id: str = "anonymous"):
        self.session = neo4j_session
        self.user_id = user_id
        self.llm = get_llm_client()
        self.min_confidence = 0.6

    def _user_filter(self, alias: str = "d") -> str:
        """Return a Cypher WHERE clause fragment for user isolation."""
        return f"({alias}.user_id = $user_id OR {alias}.user_id IS NULL)"

    async def analyze_decision_pair(
        self, decision_a: dict, decision_b: dict
    ) -> Optional[dict]:
        """Analyze two decisions for SUPERSEDES or CONTRADICTS relationship.

        Args:
            decision_a: First decision dict with id, trigger, decision, created_at
            decision_b: Second decision dict with id, trigger, decision, created_at

        Returns:
            Dict with relationship type and confidence, or None
        """
        prompt = f"""Analyze if these two decisions have a significant relationship.

Types:
- SUPERSEDES: The newer decision explicitly replaces or changes the older decision
- CONTRADICTS: The decisions fundamentally conflict (choosing opposite approaches)
- NONE: No significant relationship (different topics or compatible decisions)

## Decision A ({decision_a.get("created_at", "unknown date")}):
Trigger: {decision_a.get("trigger", "")}
Decision: {decision_a.get("decision", "")}
Rationale: {decision_a.get("rationale", "")}

## Decision B ({decision_b.get("created_at", "unknown date")}):
Trigger: {decision_b.get("trigger", "")}
Decision: {decision_b.get("decision", "")}
Rationale: {decision_b.get("rationale", "")}

Important guidelines:
- SUPERSEDES means the newer decision explicitly changes or replaces the older one
- CONTRADICTS means the decisions are fundamentally incompatible
- If decisions are about different topics or are compatible, return NONE
- Consider temporal order: only newer decisions can supersede older ones

Return a JSON object:
{{
  "relationship": "SUPERSEDES" | "CONTRADICTS" | "NONE",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation"
}}

Return ONLY valid JSON, no markdown or explanation."""

        try:
            response = await self.llm.generate(prompt, temperature=0.3)

            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]

            result = json.loads(text)

            if result.get("relationship") == "NONE":
                return None

            return {
                "type": result.get("relationship"),
                "confidence": result.get("confidence", 0.5),
                "reasoning": result.get("reasoning", ""),
            }

        except JSONDecodeError as e:
            logger.error(f"Failed to parse decision analysis response: {e}")
            return None
        except (TimeoutError, ConnectionError) as e:
            logger.error(f"LLM connection error during decision analysis: {e}")
            return None
        except Exception as e:
            # Catch-all for unexpected LLM API errors
            logger.error(f"Unexpected error analyzing pair: {e}")
            return None

    async def analyze_all_pairs(self) -> dict:
        """Batch analyze all user's decisions for SUPERSEDES/CONTRADICTS relationships.

        Groups decisions by shared entities for efficiency, then analyzes pairs.

        Returns:
            Dict with 'supersedes' and 'contradicts' lists
        """
        decisions = await self._get_all_decisions_with_entities()

        if len(decisions) < 2:
            return {"supersedes": [], "contradicts": []}

        # Group by shared entities for efficiency
        groups = self._group_by_shared_entities(decisions, min_shared=2)

        results = {"supersedes": [], "contradicts": []}
        analyzed_pairs = set()  # Avoid analyzing same pair twice

        for group in groups:
            for a, b in itertools.combinations(group, 2):
                # Create pair key to avoid duplicates
                pair_key = tuple(sorted([a["id"], b["id"]]))
                if pair_key in analyzed_pairs:
                    continue
                analyzed_pairs.add(pair_key)

                rel = await self.analyze_decision_pair(a, b)

                if rel and rel["confidence"] >= self.min_confidence:
                    rel_type = rel["type"]

                    if rel_type == "SUPERSEDES":
                        # Determine which supersedes which based on date
                        if a.get("created_at", "") > b.get("created_at", ""):
                            newer, older = a, b
                        else:
                            newer, older = b, a

                        results["supersedes"].append(
                            {
                                "from_id": newer["id"],
                                "to_id": older["id"],
                                "confidence": rel["confidence"],
                                "reasoning": rel.get("reasoning", ""),
                            }
                        )

                    elif rel_type == "CONTRADICTS":
                        results["contradicts"].append(
                            {
                                "from_id": a["id"],
                                "to_id": b["id"],
                                "confidence": rel["confidence"],
                                "reasoning": rel.get("reasoning", ""),
                            }
                        )

        return results

    async def save_relationships(self, analysis_results: dict) -> dict:
        """Save analyzed relationships to Neo4j.

        Args:
            analysis_results: Output from analyze_all_pairs()

        Returns:
            Statistics about saved relationships
        """
        stats = {"supersedes_created": 0, "contradicts_created": 0}

        for rel in analysis_results.get("supersedes", []):
            # Part 14 (graphiti bi-temporal): Add valid_at / invalid_at timestamps.
            # - valid_at: when the superseding decision became valid (its created_at)
            # - invalid_at: when the older decision stopped being valid (same moment)
            # This enables point-in-time graph queries ("what was the architecture on X?")
            await self.session.run(
                """
                MATCH (newer:DecisionTrace {id: $from_id})
                MATCH (older:DecisionTrace {id: $to_id})
                MERGE (newer)-[r:SUPERSEDES]->(older)
                SET r.confidence = $confidence,
                    r.reasoning = $reasoning,
                    r.analyzed_at = datetime(),
                    r.valid_at = COALESCE(newer.created_at, toString(datetime())),
                    r.invalid_at = null
                WITH older, r
                SET older.expired_at = COALESCE(newer.created_at, toString(datetime()))
                """,
                from_id=rel["from_id"],
                to_id=rel["to_id"],
                confidence=rel["confidence"],
                reasoning=rel.get("reasoning", ""),
            )
            # Also mark all INVOLVES edges from the superseded decision as invalid
            # (graphiti pattern: entity-entity relationships gain temporal bounds)
            await self.session.run(
                """
                MATCH (older:DecisionTrace {id: $to_id})-[inv:INVOLVES]->(e:Entity)
                WHERE inv.invalid_at IS NULL
                MATCH (newer:DecisionTrace {id: $from_id})
                SET inv.invalid_at = COALESCE(newer.created_at, toString(datetime()))
                """,
                from_id=rel["from_id"],
                to_id=rel["to_id"],
            )
            stats["supersedes_created"] += 1

        for rel in analysis_results.get("contradicts", []):
            await self.session.run(
                """
                MATCH (d1:DecisionTrace {id: $from_id})
                MATCH (d2:DecisionTrace {id: $to_id})
                MERGE (d1)-[r:CONTRADICTS]->(d2)
                SET r.confidence = $confidence,
                    r.reasoning = $reasoning,
                    r.analyzed_at = datetime()
                """,
                from_id=rel["from_id"],
                to_id=rel["to_id"],
                confidence=rel["confidence"],
                reasoning=rel.get("reasoning", ""),
            )
            stats["contradicts_created"] += 1

        return stats

    async def detect_contradictions_for_decision(self, decision_id: str) -> list[dict]:
        """Find decisions that contradict a specific decision.

        Only searches within the user's decisions.

        Args:
            decision_id: The decision to check

        Returns:
            List of contradicting decisions with confidence scores
        """
        # First check existing CONTRADICTS relationships (user-scoped)
        result = await self.session.run(
            """
            MATCH (d:DecisionTrace {id: $id})-[r:CONTRADICTS]-(other:DecisionTrace)
            WHERE (d.user_id = $user_id OR d.user_id IS NULL)
            AND (other.user_id = $user_id OR other.user_id IS NULL)
            RETURN other.id AS id,
                   other.trigger AS trigger,
                   other.decision AS decision,
                   other.created_at AS created_at,
                   r.confidence AS confidence,
                   r.reasoning AS reasoning
            """,
            id=decision_id,
            user_id=self.user_id,
        )

        existing = [dict(record) async for record in result]
        if existing:
            return existing

        # If no existing relationships, analyze similar decisions
        target = await self._get_decision(decision_id)
        if not target:
            return []

        # Get decisions with shared entities (user-scoped)
        similar = await self._get_decisions_with_shared_entities(
            decision_id, min_shared=1
        )

        contradictions = []
        for other in similar:
            rel = await self.analyze_decision_pair(target, other)
            if (
                rel
                and rel["type"] == "CONTRADICTS"
                and rel["confidence"] >= self.min_confidence
            ):
                contradictions.append(
                    {
                        "id": other["id"],
                        "trigger": other.get("trigger", ""),
                        "decision": other.get("decision", ""),
                        "created_at": other.get("created_at", ""),
                        "confidence": rel["confidence"],
                        "reasoning": rel.get("reasoning", ""),
                    }
                )

                # Save the relationship
                await self.session.run(
                    """
                    MATCH (d1:DecisionTrace {id: $id1})
                    MATCH (d2:DecisionTrace {id: $id2})
                    MERGE (d1)-[r:CONTRADICTS]->(d2)
                    SET r.confidence = $confidence,
                        r.reasoning = $reasoning,
                        r.analyzed_at = datetime()
                    """,
                    id1=decision_id,
                    id2=other["id"],
                    confidence=rel["confidence"],
                    reasoning=rel.get("reasoning", ""),
                )

        return contradictions

    async def get_entity_timeline(self, entity_name: str) -> list[dict]:
        """Get chronological decisions about an entity for the current user.

        Args:
            entity_name: The entity name to search for

        Returns:
            List of decisions ordered by creation date
        """
        result = await self.session.run(
            """
            MATCH (e:Entity)
            WHERE toLower(e.name) = toLower($name)
            OR ANY(alias IN COALESCE(e.aliases, []) WHERE toLower(alias) = toLower($name))
            WITH e
            MATCH (d:DecisionTrace)-[:INVOLVES]->(e)
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            OPTIONAL MATCH (d)-[sup:SUPERSEDES]->(superseded:DecisionTrace)
            WHERE superseded.user_id = $user_id OR superseded.user_id IS NULL
            OPTIONAL MATCH (d)-[con:CONTRADICTS]-(conflicting:DecisionTrace)
            WHERE conflicting.user_id = $user_id OR conflicting.user_id IS NULL
            RETURN d.id AS id,
                   d.trigger AS trigger,
                   COALESCE(d.agent_decision, d.decision) AS decision,
                   COALESCE(d.agent_rationale, d.rationale) AS rationale,
                   d.created_at AS created_at,
                   d.source AS source,
                   collect(DISTINCT superseded.id) AS supersedes,
                   collect(DISTINCT conflicting.id) AS conflicts_with
            ORDER BY d.created_at ASC
            """,
            name=entity_name,
            user_id=self.user_id,
        )

        return [dict(record) async for record in result]

    async def get_decision_evolution(self, decision_id: str) -> dict:
        """Get the evolution chain for a decision.

        Returns decisions that influenced this one and decisions it supersedes.
        Only includes user's decisions.
        """
        result = await self.session.run(
            """
            MATCH (d:DecisionTrace {id: $id})
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            OPTIONAL MATCH (d)-[:INFLUENCED_BY]->(influenced_by:DecisionTrace)
            WHERE influenced_by.user_id = $user_id OR influenced_by.user_id IS NULL
            OPTIONAL MATCH (d)-[:SUPERSEDES]->(supersedes:DecisionTrace)
            WHERE supersedes.user_id = $user_id OR supersedes.user_id IS NULL
            OPTIONAL MATCH (superseded_by:DecisionTrace)-[:SUPERSEDES]->(d)
            WHERE superseded_by.user_id = $user_id OR superseded_by.user_id IS NULL
            RETURN d.id AS id,
                   d.trigger AS trigger,
                   COALESCE(d.agent_decision, d.decision) AS decision,
                   d.created_at AS created_at,
                   collect(DISTINCT {
                       id: influenced_by.id,
                       trigger: influenced_by.trigger,
                       created_at: influenced_by.created_at
                   }) AS influenced_by,
                   collect(DISTINCT {
                       id: supersedes.id,
                       trigger: supersedes.trigger,
                       created_at: supersedes.created_at
                   }) AS supersedes,
                   collect(DISTINCT {
                       id: superseded_by.id,
                       trigger: superseded_by.trigger,
                       created_at: superseded_by.created_at
                   }) AS superseded_by
            """,
            id=decision_id,
            user_id=self.user_id,
        )

        record = await result.single()
        if not record:
            return {}

        return {
            "decision": {
                "id": record["id"],
                "trigger": record["trigger"],
                "decision": record["decision"],
                "created_at": record["created_at"],
            },
            "influenced_by": [r for r in record["influenced_by"] if r.get("id")],
            "supersedes": [r for r in record["supersedes"] if r.get("id")],
            "superseded_by": [r for r in record["superseded_by"] if r.get("id")],
        }

    async def _get_all_decisions_with_entities(self) -> list[dict]:
        """Get all user's decisions with their associated entities."""
        result = await self.session.run(
            """
            MATCH (d:DecisionTrace)
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            OPTIONAL MATCH (d)-[:INVOLVES]->(e:Entity)
            RETURN d.id AS id,
                   d.trigger AS trigger,
                   COALESCE(d.agent_decision, d.decision) AS decision,
                   COALESCE(d.agent_rationale, d.rationale) AS rationale,
                   d.created_at AS created_at,
                   collect(e.name) AS entities
            """,
            user_id=self.user_id,
        )
        return [dict(record) async for record in result]

    async def _get_decision(self, decision_id: str) -> Optional[dict]:
        """Get a single decision by ID (user-scoped)."""
        result = await self.session.run(
            """
            MATCH (d:DecisionTrace {id: $id})
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            RETURN d.id AS id,
                   d.trigger AS trigger,
                   COALESCE(d.agent_decision, d.decision) AS decision,
                   COALESCE(d.agent_rationale, d.rationale) AS rationale,
                   d.created_at AS created_at
            """,
            id=decision_id,
            user_id=self.user_id,
        )
        record = await result.single()
        return dict(record) if record else None

    async def _get_decisions_with_shared_entities(
        self, decision_id: str, min_shared: int = 1
    ) -> list[dict]:
        """Get user's decisions that share entities with the given decision."""
        result = await self.session.run(
            """
            MATCH (d:DecisionTrace {id: $id})-[:INVOLVES]->(e:Entity)<-[:INVOLVES]-(other:DecisionTrace)
            WHERE other.id <> d.id
            AND (other.user_id = $user_id OR other.user_id IS NULL)
            WITH other, count(DISTINCT e) AS shared_count
            WHERE shared_count >= $min_shared
            RETURN other.id AS id,
                   other.trigger AS trigger,
                   other.decision AS decision,
                   other.rationale AS rationale,
                   other.created_at AS created_at,
                   shared_count
            ORDER BY shared_count DESC
            """,
            id=decision_id,
            min_shared=min_shared,
            user_id=self.user_id,
        )
        return [dict(record) async for record in result]

    def _group_by_shared_entities(
        self, decisions: list[dict], min_shared: int = 2
    ) -> list[list[dict]]:
        """Group decisions by shared entities.

        Args:
            decisions: List of decisions with 'entities' field
            min_shared: Minimum shared entities to group together

        Returns:
            List of groups, where each group shares at least min_shared entities
        """
        # Build entity -> decisions mapping
        entity_to_decisions = {}
        for d in decisions:
            for entity in d.get("entities", []):
                if entity:
                    if entity not in entity_to_decisions:
                        entity_to_decisions[entity] = []
                    entity_to_decisions[entity].append(d)

        # Find groups with sufficient overlap
        groups = []
        processed = set()

        for d in decisions:
            if d["id"] in processed:
                continue

            entities = set(d.get("entities", []))
            if not entities:
                continue

            group = [d]
            processed.add(d["id"])

            for other in decisions:
                if other["id"] in processed:
                    continue

                other_entities = set(other.get("entities", []))
                shared = len(entities & other_entities)

                if shared >= min_shared:
                    group.append(other)
                    processed.add(other["id"])

            if len(group) > 1:
                groups.append(group)

        return groups


# Factory function
def get_decision_analyzer(
    neo4j_session, user_id: str = "anonymous"
) -> DecisionAnalyzer:
    """Create a DecisionAnalyzer instance with the given Neo4j session."""
    return DecisionAnalyzer(neo4j_session, user_id=user_id)
