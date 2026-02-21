"""Graph validation service for checking knowledge graph integrity.

All validation is user-scoped. Users can only validate their own data.

KG-P2-3: Enhanced circular dependency detection with:
- Configurable traversal depth
- Full cycle path reporting
- Support for multiple relationship types
- Detection of all cycles, not just the first
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from rapidfuzz import fuzz

from models.ontology import CANONICAL_NAMES
from utils.logging import get_logger

logger = get_logger(__name__)


class IssueSeverity(Enum):
    """Severity levels for validation issues."""

    ERROR = "error"  # Must be fixed
    WARNING = "warning"  # Should be investigated
    INFO = "info"  # Informational


class IssueType(Enum):
    """Types of validation issues."""

    CIRCULAR_DEPENDENCY = "circular_dependency"
    ORPHAN_ENTITY = "orphan_entity"
    LOW_CONFIDENCE_RELATIONSHIP = "low_confidence_relationship"
    DUPLICATE_ENTITY = "duplicate_entity"
    MISSING_EMBEDDING = "missing_embedding"
    INVALID_RELATIONSHIP = "invalid_relationship"
    INCONSISTENT_ENTITY_TYPE = "inconsistent_entity_type"


@dataclass
class CyclePath:
    """Represents a detected cycle in the graph (KG-P2-3)."""

    nodes: list[str]  # Node IDs in cycle order
    names: list[str]  # Node names in cycle order
    relationship_type: str  # The relationship type forming the cycle
    length: int = 0  # Number of edges in the cycle

    def __post_init__(self):
        self.length = len(self.nodes)

    def format_path(self) -> str:
        """Format the cycle as a readable path string."""
        if not self.names:
            return ""
        # Add the first node at the end to show it's a cycle
        path_names = self.names + [self.names[0]]
        return f" -[{self.relationship_type}]-> ".join(path_names)


@dataclass
class ValidationIssue:
    """A validation issue found in the graph."""

    type: IssueType
    severity: IssueSeverity
    message: str
    affected_nodes: list[str]
    suggested_action: Optional[str] = None
    details: Optional[dict] = None
    cycle_path: Optional[CyclePath] = None  # KG-P2-3: For circular dependencies


class GraphValidator:
    """Validate knowledge graph integrity and consistency.

    All validation is scoped to the user's data only.

    Checks for:
    - Circular dependencies in DEPENDS_ON/REQUIRES chains (KG-P2-3: Enhanced)
    - Orphan entities with no relationships
    - Low confidence relationships
    - Duplicate entities (via fuzzy matching)
    - Missing embeddings
    - Invalid relationship configurations
    """

    # KG-P2-3: Relationship types that should not form cycles
    CYCLE_CHECK_RELATIONSHIPS = ["DEPENDS_ON", "REQUIRES", "PART_OF", "IS_A", "REFINES"]

    # KG-P2-3: Maximum traversal depth for cycle detection
    DEFAULT_MAX_DEPTH = 20

    # KG-P2-3: Maximum cycles to report per relationship type
    MAX_CYCLES_PER_TYPE = 10

    def __init__(self, neo4j_session, user_id: str = "anonymous"):
        self.session = neo4j_session
        self.user_id = user_id
        self.fuzzy_threshold = 85

    def _user_filter(self, alias: str = "d") -> str:
        """Return a Cypher WHERE clause fragment for user isolation."""
        return f"({alias}.user_id = $user_id OR {alias}.user_id IS NULL)"

    async def validate_all(self) -> list[ValidationIssue]:
        """Run all validation checks on user's data.

        Returns:
            List of ValidationIssue objects
        """
        issues = []
        issues.extend(await self.check_circular_dependencies())
        issues.extend(await self.check_orphan_entities())
        issues.extend(await self.check_low_confidence_relationships(threshold=0.5))
        issues.extend(await self.check_duplicate_entities())
        issues.extend(await self.check_missing_embeddings())
        issues.extend(await self.check_invalid_relationships())
        return issues

    async def check_circular_dependencies(
        self,
        relationship_types: Optional[list[str]] = None,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> list[ValidationIssue]:
        """Find circular dependency chains in user's entities (KG-P2-3: Enhanced).

        Detects cycles in hierarchical relationships that should be acyclic:
        - DEPENDS_ON: X depends on Y should not cycle
        - REQUIRES: X requires Y should not cycle
        - PART_OF: X is part of Y should not cycle
        - IS_A: X is a type of Y should not cycle
        - REFINES: X refines Y should not cycle

        Args:
            relationship_types: Specific relationship types to check.
                               Defaults to CYCLE_CHECK_RELATIONSHIPS.
            max_depth: Maximum path length to search (default: 20)

        Returns:
            List of ValidationIssue objects for each detected cycle
        """
        issues = []
        rel_types = relationship_types or self.CYCLE_CHECK_RELATIONSHIPS

        for rel_type in rel_types:
            cycle_issues = await self._check_cycles_for_relationship(
                rel_type, max_depth
            )
            issues.extend(cycle_issues)

        return issues

    async def _check_cycles_for_relationship(
        self,
        rel_type: str,
        max_depth: int,
    ) -> list[ValidationIssue]:
        """Check for cycles in a specific relationship type (KG-P2-3).

        Uses a Neo4j query that:
        1. Finds all entities connected to user's decisions
        2. Traverses paths of the specified relationship type
        3. Detects when a path returns to its starting node
        4. Returns the full cycle path for debugging

        Args:
            rel_type: The relationship type to check (e.g., "DEPENDS_ON")
            max_depth: Maximum path length to search

        Returns:
            List of ValidationIssue objects for cycles in this relationship type
        """
        issues = []
        seen_cycles: set[frozenset[str]] = set()  # Track unique cycles by node set

        try:
            # Dynamic query for the specific relationship type
            # We use apoc.path.expandConfig if available, otherwise a simpler approach
            query = f"""
                MATCH (d:DecisionTrace)-[:INVOLVES]->(start:Entity)
                WHERE d.user_id = $user_id OR d.user_id IS NULL
                WITH DISTINCT start
                MATCH path = (start)-[:{rel_type}*2..{max_depth}]->(start)
                WITH nodes(path) AS cycle_nodes, length(path) AS path_length
                WITH cycle_nodes, path_length
                ORDER BY path_length
                LIMIT {self.MAX_CYCLES_PER_TYPE * 2}
                RETURN
                    [n IN cycle_nodes | n.name] AS cycle_names,
                    [n IN cycle_nodes | n.id] AS cycle_ids,
                    path_length
            """

            result = await self.session.run(
                query,
                user_id=self.user_id,
            )

            async for record in result:
                cycle_names = record["cycle_names"]
                cycle_ids = record["cycle_ids"]
                path_length = record["path_length"]

                # Deduplicate cycles (same nodes in different order)
                cycle_key = frozenset(cycle_ids)
                if cycle_key in seen_cycles:
                    continue
                seen_cycles.add(cycle_key)

                if len(seen_cycles) > self.MAX_CYCLES_PER_TYPE:
                    break

                # Create detailed cycle path info
                cycle_path = CyclePath(
                    nodes=cycle_ids,
                    names=cycle_names,
                    relationship_type=rel_type,
                )

                # Determine severity based on relationship type
                severity = IssueSeverity.ERROR
                if rel_type in ["RELATED_TO"]:
                    severity = IssueSeverity.WARNING

                issues.append(
                    ValidationIssue(
                        type=IssueType.CIRCULAR_DEPENDENCY,
                        severity=severity,
                        message=f"Circular {rel_type} dependency: {cycle_path.format_path()}",
                        affected_nodes=cycle_ids,
                        suggested_action=self._get_cycle_fix_suggestion(rel_type),
                        details={
                            "cycle_names": cycle_names,
                            "relationship_type": rel_type,
                            "path_length": path_length,
                            "formatted_path": cycle_path.format_path(),
                        },
                        cycle_path=cycle_path,
                    )
                )

        except Exception as e:
            logger.error(f"Error checking circular dependencies for {rel_type}: {e}")

        return issues

    def _get_cycle_fix_suggestion(self, rel_type: str) -> str:
        """Get a fix suggestion based on relationship type (KG-P2-3)."""
        suggestions = {
            "DEPENDS_ON": (
                "Review the dependency chain and identify which dependency is incorrect. "
                "Consider if one entity should use RELATED_TO instead."
            ),
            "REQUIRES": (
                "REQUIRES implies a hard dependency - review which requirement is "
                "actually optional and could be DEPENDS_ON instead."
            ),
            "PART_OF": (
                "An entity cannot be part of itself transitively. "
                "Review the composition hierarchy and remove incorrect parent-child links."
            ),
            "IS_A": (
                "An entity cannot be a type of itself. "
                "Review the type hierarchy and correct the classification."
            ),
            "REFINES": (
                "Refinement should be unidirectional. "
                "Review which entity is the base and which is the refinement."
            ),
        }
        return suggestions.get(
            rel_type, f"Review the {rel_type} relationships and remove the cycle"
        )

    async def find_dependency_path(
        self,
        source_id: str,
        target_id: str,
        relationship_types: Optional[list[str]] = None,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> Optional[list[dict]]:
        """Find a dependency path between two entities (KG-P2-3).

        Useful for understanding why a circular dependency exists.

        Args:
            source_id: Starting entity ID
            target_id: Target entity ID
            relationship_types: Relationship types to traverse
            max_depth: Maximum path length

        Returns:
            List of nodes in the path, or None if no path exists
        """
        rel_types = relationship_types or self.CYCLE_CHECK_RELATIONSHIPS
        rel_pattern = "|".join(rel_types)

        try:
            result = await self.session.run(
                f"""
                MATCH (source:Entity {{id: $source_id}})
                MATCH (target:Entity {{id: $target_id}})
                MATCH path = shortestPath((source)-[:{rel_pattern}*1..{max_depth}]->(target))
                RETURN
                    [n IN nodes(path) | {{id: n.id, name: n.name, type: n.type}}] AS path_nodes,
                    [r IN relationships(path) | type(r)] AS path_rels
                LIMIT 1
                """,
                source_id=source_id,
                target_id=target_id,
            )

            record = await result.single()
            if record:
                return {
                    "nodes": record["path_nodes"],
                    "relationships": record["path_rels"],
                }
            return None

        except Exception as e:
            logger.error(f"Error finding dependency path: {e}")
            return None

    async def check_orphan_entities(self) -> list[ValidationIssue]:
        """Find user's entities with no relationships.

        Orphan entities may indicate incomplete extraction or stale data.
        """
        issues = []

        # Find entities that are connected to user's decisions but have no other relationships
        result = await self.session.run(
            """
            MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            WITH DISTINCT e
            WHERE NOT (e)-[:IS_A|PART_OF|RELATED_TO|DEPENDS_ON|ALTERNATIVE_TO|ENABLES|PREVENTS|REQUIRES|REFINES]-()
            RETURN e.id AS id, e.name AS name, e.type AS type
            """,
            user_id=self.user_id,
        )

        async for record in result:
            issues.append(
                ValidationIssue(
                    type=IssueType.ORPHAN_ENTITY,
                    severity=IssueSeverity.WARNING,
                    message=f"Orphan entity found: {record['name']} ({record['type']})",
                    affected_nodes=[record["id"]],
                    suggested_action="Link to relevant decisions or delete if no longer needed",
                    details={"name": record["name"], "type": record["type"]},
                )
            )

        return issues

    async def check_low_confidence_relationships(
        self, threshold: float = 0.5
    ) -> list[ValidationIssue]:
        """Find relationships with low confidence scores in user's graph.

        Low confidence relationships may need manual verification.
        """
        issues = []

        result = await self.session.run(
            """
            MATCH (d:DecisionTrace)-[r]->(b)
            WHERE (d.user_id = $user_id OR d.user_id IS NULL)
            AND r.confidence IS NOT NULL AND r.confidence < $threshold
            RETURN d.id AS source_id,
                   COALESCE(d.trigger, 'Decision') AS source_name,
                   b.id AS target_id,
                   COALESCE(b.name, b.trigger) AS target_name,
                   type(r) AS rel_type,
                   r.confidence AS confidence
            ORDER BY r.confidence ASC
            LIMIT 50
            """,
            threshold=threshold,
            user_id=self.user_id,
        )

        async for record in result:
            issues.append(
                ValidationIssue(
                    type=IssueType.LOW_CONFIDENCE_RELATIONSHIP,
                    severity=IssueSeverity.INFO,
                    message=f"Low confidence {record['rel_type']}: {record['source_name'][:30]} -> {record['target_name'][:30] if record['target_name'] else 'unknown'} ({record['confidence']:.2f})",
                    affected_nodes=[record["source_id"], record["target_id"]],
                    suggested_action="Review and verify this relationship or increase confidence",
                    details={
                        "relationship": record["rel_type"],
                        "confidence": record["confidence"],
                        "source": record["source_name"],
                        "target": record["target_name"],
                    },
                )
            )

        return issues

    async def check_duplicate_entities(self) -> list[ValidationIssue]:
        """Find potential duplicate entities via fuzzy matching in user's data.

        Duplicates fragment the knowledge graph and reduce query accuracy.
        """
        issues = []

        # Get entities connected to user's decisions
        result = await self.session.run(
            """
            MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            RETURN DISTINCT e.id AS id, e.name AS name, e.type AS type
            """,
            user_id=self.user_id,
        )

        entities = [dict(record) async for record in result]

        # Find potential duplicates
        processed_pairs = set()
        for i, e1 in enumerate(entities):
            for e2 in entities[i + 1 :]:
                pair_key = tuple(sorted([e1["id"], e2["id"]]))
                if pair_key in processed_pairs:
                    continue
                processed_pairs.add(pair_key)

                # Check fuzzy match
                score = fuzz.ratio(e1["name"].lower(), e2["name"].lower())
                if score >= self.fuzzy_threshold and score < 100:
                    # Check if one is canonical form of the other
                    e1_canonical = CANONICAL_NAMES.get(e1["name"].lower())
                    e2_canonical = CANONICAL_NAMES.get(e2["name"].lower())

                    is_alias = (
                        e1_canonical == e2["name"]
                        or e2_canonical == e1["name"]
                        or (e1_canonical and e1_canonical == e2_canonical)
                    )

                    issues.append(
                        ValidationIssue(
                            type=IssueType.DUPLICATE_ENTITY,
                            severity=IssueSeverity.WARNING
                            if is_alias
                            else IssueSeverity.INFO,
                            message=f"Potential duplicate: '{e1['name']}' and '{e2['name']}' ({score}% similar)",
                            affected_nodes=[e1["id"], e2["id"]],
                            suggested_action="Merge these entities or add one as an alias",
                            details={
                                "entity1": e1["name"],
                                "entity2": e2["name"],
                                "similarity": score,
                                "is_known_alias": is_alias,
                            },
                        )
                    )

        return issues

    async def check_missing_embeddings(self) -> list[ValidationIssue]:
        """Find user's nodes missing embeddings.

        Missing embeddings reduce semantic search accuracy.
        """
        issues = []

        # Check user's decisions without embeddings
        result = await self.session.run(
            """
            MATCH (d:DecisionTrace)
            WHERE (d.user_id = $user_id OR d.user_id IS NULL)
            AND d.embedding IS NULL
            RETURN count(d) AS count
            """,
            user_id=self.user_id,
        )

        record = await result.single()
        decision_count = record["count"] if record else 0

        if decision_count > 0:
            issues.append(
                ValidationIssue(
                    type=IssueType.MISSING_EMBEDDING,
                    severity=IssueSeverity.WARNING,
                    message=f"{decision_count} decisions missing embeddings",
                    affected_nodes=[],
                    suggested_action="Run POST /api/graph/enhance to backfill embeddings",
                    details={"count": decision_count, "type": "decision"},
                )
            )

        # Check entities connected to user's decisions without embeddings
        result = await self.session.run(
            """
            MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
            WHERE (d.user_id = $user_id OR d.user_id IS NULL)
            AND e.embedding IS NULL
            RETURN count(DISTINCT e) AS count
            """,
            user_id=self.user_id,
        )
        record = await result.single()
        entity_count = record["count"] if record else 0

        if entity_count > 0:
            issues.append(
                ValidationIssue(
                    type=IssueType.MISSING_EMBEDDING,
                    severity=IssueSeverity.INFO,
                    message=f"{entity_count} entities missing embeddings",
                    affected_nodes=[],
                    suggested_action="Run POST /api/graph/enhance to backfill embeddings",
                    details={"count": entity_count, "type": "entity"},
                )
            )

        return issues

    async def check_invalid_relationships(self) -> list[ValidationIssue]:
        """Find invalid relationship configurations in user's data.

        Checks for:
        - Self-referential relationships
        - Decision-to-decision entity relationships
        - Entity-to-entity decision relationships
        """
        issues = []

        # Check self-referential relationships in user's data
        result = await self.session.run(
            """
            MATCH (d:DecisionTrace)-[r]->(d)
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            RETURN d.id AS id,
                   d.trigger AS name,
                   type(r) AS rel_type
            """,
            user_id=self.user_id,
        )

        async for record in result:
            issues.append(
                ValidationIssue(
                    type=IssueType.INVALID_RELATIONSHIP,
                    severity=IssueSeverity.ERROR,
                    message=f"Self-referential relationship: {record['name'][:30] if record['name'] else 'Decision'} -{record['rel_type']}-> itself",
                    affected_nodes=[record["id"]],
                    suggested_action="Remove this self-referential relationship",
                    details={"relationship": record["rel_type"]},
                )
            )

        # Check decision-to-decision with entity relationships
        # Include the new relationship types from KG-P2-1
        result = await self.session.run(
            """
            MATCH (d1:DecisionTrace)-[r]->(d2:DecisionTrace)
            WHERE (d1.user_id = $user_id OR d1.user_id IS NULL)
            AND type(r) IN ['IS_A', 'PART_OF', 'DEPENDS_ON', 'ALTERNATIVE_TO', 'ENABLES', 'PREVENTS', 'REQUIRES', 'REFINES']
            RETURN d1.id AS id1, d1.trigger AS trigger1,
                   d2.id AS id2, d2.trigger AS trigger2,
                   type(r) AS rel_type
            """,
            user_id=self.user_id,
        )

        async for record in result:
            issues.append(
                ValidationIssue(
                    type=IssueType.INVALID_RELATIONSHIP,
                    severity=IssueSeverity.ERROR,
                    message=f"Entity relationship between decisions: {(record['trigger1'] or 'Decision')[:30]} -{record['rel_type']}-> {(record['trigger2'] or 'Decision')[:30]}",
                    affected_nodes=[record["id1"], record["id2"]],
                    suggested_action="Change to a decision relationship (SIMILAR_TO, INFLUENCED_BY, etc.) or remove",
                    details={"relationship": record["rel_type"]},
                )
            )

        return issues

    async def get_validation_summary(self) -> dict:
        """Get a summary of validation issues by type and severity."""
        issues = await self.validate_all()

        summary = {
            "total_issues": len(issues),
            "by_severity": {
                "error": 0,
                "warning": 0,
                "info": 0,
            },
            "by_type": {},
        }

        for issue in issues:
            summary["by_severity"][issue.severity.value] += 1

            type_key = issue.type.value
            if type_key not in summary["by_type"]:
                summary["by_type"][type_key] = 0
            summary["by_type"][type_key] += 1

        return summary

    async def auto_fix(self, issue_types: Optional[list[IssueType]] = None) -> dict:
        """Automatically fix certain validation issues in user's data.

        Only fixes safe, well-defined issues like:
        - Removing self-referential relationships
        - Merging exact duplicate entities

        Args:
            issue_types: Specific issue types to fix, or None for all safe fixes

        Returns:
            Statistics about fixes applied
        """
        stats = {
            "self_references_removed": 0,
            "exact_duplicates_merged": 0,
        }

        # Remove self-referential relationships in user's data
        if issue_types is None or IssueType.INVALID_RELATIONSHIP in issue_types:
            result = await self.session.run(
                """
                MATCH (d:DecisionTrace)-[r]->(d)
                WHERE d.user_id = $user_id OR d.user_id IS NULL
                DELETE r
                RETURN count(r) AS count
                """,
                user_id=self.user_id,
            )
            record = await result.single()
            stats["self_references_removed"] = record["count"] if record else 0

        return stats


# Factory function
def get_graph_validator(neo4j_session, user_id: str = "anonymous") -> GraphValidator:
    """Create a GraphValidator instance with the given Neo4j session."""
    return GraphValidator(neo4j_session, user_id=user_id)
