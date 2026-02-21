"""Assumption monitor — Part 11.

Detects when a decision's stated assumptions have been invalidated by
newer decisions.  This is the "sleeping decision" problem: a decision made
under assumption X is now running on a codebase where X is no longer true.

Algorithm:
1. For each decision D with non-empty `assumptions[]`
2. Load all decisions made AFTER D
3. For each later decision L, check whether L's trigger or context
   contradicts or supersedes any assumption of D
4. If yes → flag D as having an invalidated assumption

Contradiction detection uses two approaches:
  a. Keyword match  — fast, zero LLM calls
  b. Embedding similarity (optional) — catches semantic contradictions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Optional

from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class InvalidatedAssumption:
    """An assumption of a decision that has been contradicted by a newer decision."""
    decision_id: str
    decision_trigger: str
    assumption: str
    invalidating_decision_id: str
    invalidating_trigger: str
    invalidating_text: str      # The specific text that contradicts the assumption
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    confidence: float = 0.7     # How confident we are the assumption is invalidated


class AssumptionMonitor:
    """Monitor decisions for invalidated assumptions.

    Usage:
        monitor = AssumptionMonitor(neo4j_session, user_id)
        invalidated = await monitor.scan_project(project_name)
    """

    def __init__(self, session, user_id: str):
        self.session = session
        self.user_id = user_id

    def _assumption_contradicted_by(
        self, assumption: str, later_text: str
    ) -> tuple[bool, float]:
        """Check if `later_text` contradicts `assumption`.

        Returns (is_contradicted, confidence).

        Keyword-based heuristics (no LLM call):
        - Antonym pairs: "monolith" ↔ "microservices", "synchronous" ↔ "async", etc.
        - Negation: "no longer", "deprecated", "replaced", "removed"
        - Direct contradiction phrases
        """
        assumption_lower = assumption.lower()
        later_lower = later_text.lower()

        # 1. Direct negation signals in the later text
        negation_phrases = [
            "no longer", "deprecated", "replaced by", "removed", "migrated away from",
            "switched from", "moved away from", "abandoned", "dropped support for",
        ]
        for phrase in negation_phrases:
            if phrase in later_lower:
                # Check if assumption keywords appear near the negation
                assumption_words = set(assumption_lower.split())
                # Simple: if any key assumption word appears in the later text
                if any(w in later_lower for w in assumption_words if len(w) > 4):
                    return True, 0.75

        # 2. Antonym pairs
        antonym_pairs = [
            ("monolith", "microservice"),
            ("synchronous", "async"),
            ("sql", "nosql"),
            ("rest", "graphql"),
            ("rest", "grpc"),
            ("single tenant", "multi tenant"),
            ("single-tenant", "multi-tenant"),
            ("postgres", "mongodb"),
            ("postgres", "cassandra"),
            ("jwt", "session"),
            ("session", "jwt"),
            ("class", "functional"),
            ("oop", "functional"),
            ("on-premise", "cloud"),
            ("on-prem", "cloud"),
        ]
        for a, b in antonym_pairs:
            if a in assumption_lower and b in later_lower:
                return True, 0.80
            if b in assumption_lower and a in later_lower:
                return True, 0.80

        # 3. Scale assumption contradictions
        # e.g. assumption "< 100 req/s" vs later "10,000 req/s"
        import re
        assumption_numbers = re.findall(r"\b(\d[\d,]*)\s*(req|rps|users|records|gb|mb|kb|ms)", assumption_lower)
        later_numbers = re.findall(r"\b(\d[\d,]*)\s*(req|rps|users|records|gb|mb|kb|ms)", later_lower)

        for (a_num_str, a_unit) in assumption_numbers:
            for (l_num_str, l_unit) in later_numbers:
                if a_unit == l_unit:
                    try:
                        a_num = int(a_num_str.replace(",", ""))
                        l_num = int(l_num_str.replace(",", ""))
                        # If scale increased 10x → assumption likely violated
                        if l_num >= a_num * 10:
                            return True, 0.70
                    except ValueError:
                        pass

        return False, 0.0

    async def scan_project(
        self,
        project_name: Optional[str] = None,
        limit: int = 50,
    ) -> list[InvalidatedAssumption]:
        """Scan all decisions in the project for invalidated assumptions.

        Args:
            project_name: Filter to a specific project (None = all)
            limit:        Max decisions to scan
        """
        project_filter = "AND d.project_name = $project_name" if project_name else ""

        # Load decisions with non-empty assumptions
        query = f"""
        MATCH (d:DecisionTrace)
        WHERE d.user_id = $user_id
          AND d.assumptions IS NOT NULL
          AND size(d.assumptions) > 0
          {project_filter}
        RETURN d.id AS id,
               d.trigger AS trigger,
               d.assumptions AS assumptions,
               d.created_at AS created_at
        ORDER BY d.created_at ASC
        LIMIT $limit
        """

        params: dict = {"user_id": self.user_id, "limit": limit}
        if project_name:
            params["project_name"] = project_name

        try:
            result = await self.session.run(query, **params)
            decisions_with_assumptions = await result.data()
        except Exception as e:
            logger.error(f"AssumptionMonitor scan failed: {e}")
            return []

        if not decisions_with_assumptions:
            return []

        # For each decision, load later decisions and check for contradictions
        invalidated: list[InvalidatedAssumption] = []

        for row in decisions_with_assumptions:
            decision_id = row.get("id", "")
            trigger = row.get("trigger", "")
            assumptions: list[str] = row.get("assumptions") or []
            created_at_raw = row.get("created_at")

            if not assumptions or not decision_id:
                continue

            # Load decisions made AFTER this one
            later_query = f"""
            MATCH (later:DecisionTrace)
            WHERE later.user_id = $user_id
              AND later.created_at > $created_at
              {project_filter}
            RETURN later.id AS id,
                   later.trigger AS trigger,
                   later.context AS context,
                   later.agent_decision AS decision
            ORDER BY later.created_at ASC
            LIMIT 50
            """
            later_params: dict = {
                "user_id": self.user_id,
                "created_at": str(created_at_raw or ""),
            }
            if project_name:
                later_params["project_name"] = project_name

            try:
                later_result = await self.session.run(later_query, **later_params)
                later_decisions = await later_result.data()
            except Exception:
                continue

            for assumption in assumptions:
                if not assumption or len(assumption.strip()) < 5:
                    continue

                for later in later_decisions:
                    later_combined = " ".join([
                        str(later.get("trigger") or ""),
                        str(later.get("context") or ""),
                        str(later.get("decision") or ""),
                    ])

                    is_contradicted, confidence = self._assumption_contradicted_by(
                        assumption, later_combined
                    )

                    if is_contradicted:
                        invalidated.append(InvalidatedAssumption(
                            decision_id=decision_id,
                            decision_trigger=trigger,
                            assumption=assumption,
                            invalidating_decision_id=str(later.get("id") or ""),
                            invalidating_trigger=str(later.get("trigger") or ""),
                            invalidating_text=later_combined[:300],
                            confidence=confidence,
                        ))
                        # Only report first invalidating decision per assumption
                        break

        # Sort by confidence descending
        invalidated.sort(key=lambda x: x.confidence, reverse=True)
        return invalidated

    async def mark_assumption_invalidated(
        self,
        decision_id: str,
        assumption: str,
        invalidating_decision_id: str,
    ) -> None:
        """Write an ASSUMPTION_INVALIDATED relationship to Neo4j."""
        try:
            await self.session.run(
                """
                MATCH (d:DecisionTrace {id: $decision_id})
                MATCH (inv:DecisionTrace {id: $inv_id})
                MERGE (inv)-[r:ASSUMPTION_INVALIDATED]->(d)
                SET r.assumption = $assumption,
                    r.detected_at = $now
                """,
                decision_id=decision_id,
                inv_id=invalidating_decision_id,
                assumption=assumption,
                now=datetime.now(UTC).isoformat(),
            )
        except Exception as e:
            logger.error(f"Failed to write ASSUMPTION_INVALIDATED edge: {e}")
