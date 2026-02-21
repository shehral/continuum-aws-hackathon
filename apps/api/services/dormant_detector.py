"""Dormant alternative detector — Part 4.5.

Scans CandidateDecision nodes (rejected alternatives) and identifies which
ones have *never* re-surfaced in any subsequent decision.  A dormant
alternative is an unexplored path that might now be viable given how the
project has evolved.

Detection algorithm:
1. Load all CandidateDecision nodes for the user's project
2. Load all real DecisionTrace nodes (from the same time window)
3. For each candidate: check if its text is semantically similar to any
   decision made *after* the candidate was rejected
4. If no later decision covers it → it is dormant

Output is a ranked list of dormant alternatives sorted by:
  - recency of the decision that rejected them (oldest first = most likely outdated)
  - confidence of the original decision (lower confidence = more worth revisiting)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Optional

from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DormantAlternative:
    """A rejected alternative that has never been revisited."""
    candidate_id: str           # Neo4j node id of the CandidateDecision
    text: str                   # The rejected option text
    rejected_at: Optional[datetime]
    rejected_by_decision_id: str  # DecisionTrace that chose the other path
    rejected_by_trigger: str
    original_decision: str      # What was chosen instead
    days_dormant: int = 0
    reconsider_score: float = 0.0  # 0-1, higher = more worth revisiting


class DormantAlternativeDetector:
    """Detect unexplored/dormant alternatives in the knowledge graph.

    Usage:
        detector = DormantAlternativeDetector(neo4j_session, user_id)
        dormant = await detector.find_dormant_alternatives(project_name)
    """

    def __init__(self, session, user_id: str):
        self.session = session
        self.user_id = user_id

    async def find_dormant_alternatives(
        self,
        project_name: Optional[str] = None,
        min_days_dormant: int = 14,
        limit: int = 20,
    ) -> list[DormantAlternative]:
        """Find rejected alternatives not revisited in subsequent decisions.

        Args:
            project_name:     Filter to a specific project (None = all)
            min_days_dormant: Only return alternatives dormant for this many days
            limit:            Max results to return
        """
        cutoff = datetime.now(UTC) - timedelta(days=min_days_dormant)
        cutoff_iso = cutoff.isoformat()

        project_filter = "AND d.project_name = $project_name" if project_name else ""

        # Fetch CandidateDecision nodes via REJECTED_BY edges
        # CandidateDecision nodes are stored with option text in the `text` property
        # and linked to the DecisionTrace that rejected them via REJECTED_BY edge
        query = f"""
        MATCH (c:CandidateDecision)-[r:REJECTED_BY]->(d:DecisionTrace)
        WHERE d.user_id = $user_id
          {project_filter}
        OPTIONAL MATCH (d)-[:FOLLOWS]->(later:DecisionTrace)
        WHERE later.created_at > d.created_at
        WITH c, d, r, count(later) AS later_count
        WHERE later_count = 0 OR (
            NOT EXISTS {{
                MATCH (later2:DecisionTrace)
                WHERE later2.user_id = $user_id
                  AND later2.created_at > d.created_at
                  AND (
                    toLower(later2.agent_decision) CONTAINS toLower(c.text)
                    OR toLower(c.text) CONTAINS toLower(later2.agent_decision)
                  )
            }}
        )
        RETURN c.id AS candidate_id,
               c.text AS text,
               c.created_at AS rejected_at,
               d.id AS decision_id,
               d.trigger AS trigger,
               d.agent_decision AS chosen_decision,
               d.confidence AS original_confidence
        ORDER BY c.created_at ASC
        LIMIT $limit
        """

        params: dict = {
            "user_id": self.user_id,
            "limit": limit,
        }
        if project_name:
            params["project_name"] = project_name

        try:
            result = await self.session.run(query, **params)
            records = await result.data()
        except Exception as e:
            logger.error(f"Failed to query dormant alternatives: {e}")
            return []

        dormant: list[DormantAlternative] = []
        now = datetime.now(UTC)

        for row in records:
            rejected_at: Optional[datetime] = None
            days_dormant = 0

            raw_ts = row.get("rejected_at")
            if raw_ts:
                try:
                    rejected_at = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
                    days_dormant = (now - rejected_at).days
                except ValueError:
                    pass

            if days_dormant < min_days_dormant:
                continue

            # Reconsider score: older + lower original confidence = higher priority
            age_score = min(days_dormant / 365, 1.0)  # normalise to 1 year
            confidence_penalty = 1.0 - float(row.get("original_confidence") or 0.7)
            reconsider_score = round((age_score * 0.6 + confidence_penalty * 0.4), 3)

            dormant.append(DormantAlternative(
                candidate_id=str(row.get("candidate_id") or ""),
                text=str(row.get("text") or ""),
                rejected_at=rejected_at,
                rejected_by_decision_id=str(row.get("decision_id") or ""),
                rejected_by_trigger=str(row.get("trigger") or ""),
                original_decision=str(row.get("chosen_decision") or ""),
                days_dormant=days_dormant,
                reconsider_score=reconsider_score,
            ))

        # Sort by reconsider_score descending
        dormant.sort(key=lambda x: x.reconsider_score, reverse=True)
        return dormant

    async def create_candidate_decision_nodes(
        self,
        decision_id: str,
        options: list[str],
        chosen_option: str,
        created_at: Optional[datetime] = None,
    ) -> int:
        """Create CandidateDecision nodes for rejected alternatives.

        Called when a decision is saved.  For each option that was NOT chosen,
        creates a CandidateDecision node linked via REJECTED_BY to the decision.

        Returns the number of CandidateDecision nodes created.
        """
        if not options:
            return 0

        chosen_lower = chosen_option.strip().lower()
        now_iso = (created_at or datetime.now(UTC)).isoformat()
        created = 0

        for option in options:
            # Skip the chosen option (not dormant by definition)
            if option.strip().lower() == chosen_lower:
                continue
            # Skip very short options
            if len(option.strip()) < 3:
                continue

            try:
                import uuid
                candidate_id = str(uuid.uuid4())
                await self.session.run(
                    """
                    CREATE (c:CandidateDecision {
                        id: $candidate_id,
                        text: $text,
                        created_at: $created_at,
                        user_id: $user_id,
                        status: $status,
                        source: $source
                    })
                    WITH c
                    MATCH (d:DecisionTrace {id: $decision_id})
                    MERGE (c)-[:REJECTED_BY]->(d)
                    """,
                    candidate_id=candidate_id,
                    text=option.strip(),
                    created_at=now_iso,
                    decision_id=decision_id,
                    user_id=self.user_id,
                    status="rejected",
                    source="options_array",
                )
                created += 1
            except Exception as e:
                logger.error(f"Failed to create CandidateDecision node: {e}")

        return created
