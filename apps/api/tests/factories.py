"""Test data factories for Continuum API tests.

These factories create realistic test data for unit and integration tests.
"""

import random
from datetime import UTC, datetime, timedelta
from typing import Optional
from uuid import uuid4


class EntityFactory:
    """Factory for creating test entities."""

    TYPES = ["technology", "concept", "pattern", "system", "person", "organization"]

    TECHNOLOGY_NAMES = [
        "PostgreSQL",
        "MongoDB",
        "Redis",
        "Neo4j",
        "Elasticsearch",
        "React",
        "Vue.js",
        "Angular",
        "Next.js",
        "FastAPI",
        "Docker",
        "Kubernetes",
        "AWS",
        "GCP",
        "Azure",
    ]

    CONCEPT_NAMES = [
        "Microservices",
        "REST API",
        "GraphQL",
        "Caching",
        "Authentication",
        "Rate Limiting",
        "Load Balancing",
        "Event Sourcing",
        "CQRS",
    ]

    @classmethod
    def create(
        cls,
        name: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        aliases: Optional[list[str]] = None,
        embedding: Optional[list[float]] = None,
    ) -> dict:
        """Create a test entity."""
        if entity_type is None:
            entity_type = random.choice(cls.TYPES)

        if name is None:
            if entity_type == "technology":
                name = random.choice(cls.TECHNOLOGY_NAMES)
            else:
                name = random.choice(cls.CONCEPT_NAMES)

        return {
            "id": entity_id or str(uuid4()),
            "name": name,
            "type": entity_type,
            "aliases": aliases or [],
            "embedding": embedding,
            "created_at": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def create_batch(cls, count: int, **kwargs) -> list[dict]:
        """Create multiple test entities."""
        return [cls.create(**kwargs) for _ in range(count)]

    @classmethod
    def create_with_embedding(cls, name: str, entity_type: str = "technology") -> dict:
        """Create an entity with a deterministic embedding."""
        entity = cls.create(name=name, entity_type=entity_type)
        # Create embedding based on name hash for reproducibility
        seed = hash(name) % 1000000
        entity["embedding"] = [float((seed + i) % 100) / 100.0 for i in range(2048)]
        return entity


class DecisionFactory:
    """Factory for creating test decisions."""

    TRIGGERS = [
        "Need to choose a database",
        "Selecting an API framework",
        "Implementing authentication",
        "Designing the caching strategy",
        "Choosing a deployment platform",
    ]

    @classmethod
    def create(
        cls,
        trigger: Optional[str] = None,
        context: Optional[str] = None,
        options: Optional[list[str]] = None,
        decision: Optional[str] = None,
        rationale: Optional[str] = None,
        decision_id: Optional[str] = None,
        created_at: Optional[str] = None,
        entities: Optional[list[str]] = None,
    ) -> dict:
        """Create a test decision."""
        if trigger is None:
            trigger = random.choice(cls.TRIGGERS)

        if options is None:
            options = ["Option A", "Option B", "Option C"]

        if decision is None:
            decision = options[0] if options else "Default decision"

        return {
            "id": decision_id or str(uuid4()),
            "trigger": trigger,
            "context": context or f"Context for: {trigger}",
            "options": options,
            "decision": decision,
            "rationale": rationale or f"Rationale for choosing {decision}",
            "created_at": created_at or datetime.now(UTC).isoformat(),
            "entities": entities or [],
        }

    @classmethod
    def create_pair_for_comparison(
        cls,
        shared_entities: Optional[list[str]] = None,
        days_apart: int = 7,
    ) -> tuple[dict, dict]:
        """Create two related decisions for comparison testing."""
        if shared_entities is None:
            shared_entities = ["PostgreSQL", "Redis"]

        older_date = datetime.now(UTC) - timedelta(days=days_apart)
        newer_date = datetime.now(UTC)

        older = cls.create(
            trigger="Initial database decision",
            decision="Use PostgreSQL with Redis cache",
            created_at=older_date.isoformat(),
            entities=shared_entities,
        )

        newer = cls.create(
            trigger="Revised database decision",
            decision="Switch to PostgreSQL without Redis",
            created_at=newer_date.isoformat(),
            entities=shared_entities,
        )

        return older, newer

    @classmethod
    def create_batch(cls, count: int, **kwargs) -> list[dict]:
        """Create multiple test decisions."""
        return [cls.create(**kwargs) for _ in range(count)]


class RelationshipFactory:
    """Factory for creating test relationships."""

    ENTITY_RELATIONSHIPS = [
        "IS_A",
        "PART_OF",
        "DEPENDS_ON",
        "RELATED_TO",
        "ALTERNATIVE_TO",
    ]
    DECISION_RELATIONSHIPS = [
        "SIMILAR_TO",
        "INFLUENCED_BY",
        "SUPERSEDES",
        "CONTRADICTS",
    ]

    @classmethod
    def create_entity_relationship(
        cls,
        source_id: str,
        target_id: str,
        rel_type: Optional[str] = None,
        confidence: float = 0.9,
    ) -> dict:
        """Create an entity-entity relationship."""
        return {
            "source_id": source_id,
            "target_id": target_id,
            "type": rel_type or random.choice(cls.ENTITY_RELATIONSHIPS),
            "confidence": confidence,
        }

    @classmethod
    def create_decision_relationship(
        cls,
        source_id: str,
        target_id: str,
        rel_type: Optional[str] = None,
        confidence: float = 0.8,
        reasoning: str = "",
    ) -> dict:
        """Create a decision-decision relationship."""
        return {
            "source_id": source_id,
            "target_id": target_id,
            "type": rel_type or random.choice(cls.DECISION_RELATIONSHIPS),
            "confidence": confidence,
            "reasoning": reasoning or "Relationship between decisions",
        }


class Neo4jRecordFactory:
    """Factory for creating mock Neo4j query result records."""

    @classmethod
    def create_entity_record(cls, entity: dict) -> dict:
        """Create a record matching entity query result format."""
        return {
            "id": entity["id"],
            "name": entity["name"],
            "type": entity["type"],
        }

    @classmethod
    def create_decision_record(cls, decision: dict) -> dict:
        """Create a record matching decision query result format."""
        return {
            "id": decision["id"],
            "trigger": decision["trigger"],
            "context": decision.get("context", ""),
            "decision": decision["decision"],
            "rationale": decision.get("rationale", ""),
            "created_at": decision.get("created_at", ""),
        }

    @classmethod
    def create_cycle_record(cls, names: list[str], ids: list[str]) -> dict:
        """Create a record for circular dependency detection."""
        return {
            "cycle_names": names,
            "cycle_ids": ids,
            "path_length": len(ids) - 1,  # Path length is nodes - 1
        }

    @classmethod
    def create_similarity_record(cls, entity: dict, similarity: float) -> dict:
        """Create a record for embedding similarity search."""
        return {
            **cls.create_entity_record(entity),
            "similarity": similarity,
        }


class ValidationIssueFactory:
    """Factory for creating test validation issues."""

    @classmethod
    def create_circular_dependency(
        cls,
        cycle: list[str],
        ids: Optional[list[str]] = None,
    ):
        """Create a circular dependency issue."""
        from services.validator import IssueSeverity, IssueType, ValidationIssue

        return ValidationIssue(
            type=IssueType.CIRCULAR_DEPENDENCY,
            severity=IssueSeverity.ERROR,
            message=f"Circular dependency: {' -> '.join(cycle)}",
            affected_nodes=ids or [str(uuid4()) for _ in cycle],
            suggested_action="Remove the cycle",
            details={"cycle": cycle},
        )

    @classmethod
    def create_orphan_entity(cls, name: str, entity_type: str = "technology"):
        """Create an orphan entity issue."""
        from services.validator import IssueSeverity, IssueType, ValidationIssue

        return ValidationIssue(
            type=IssueType.ORPHAN_ENTITY,
            severity=IssueSeverity.WARNING,
            message=f"Orphan entity: {name} ({entity_type})",
            affected_nodes=[str(uuid4())],
            suggested_action="Link or delete",
            details={"name": name, "type": entity_type},
        )

    @classmethod
    def create_duplicate_entity(
        cls,
        name1: str,
        name2: str,
        similarity: int = 90,
    ):
        """Create a duplicate entity issue."""
        from services.validator import IssueSeverity, IssueType, ValidationIssue

        return ValidationIssue(
            type=IssueType.DUPLICATE_ENTITY,
            severity=IssueSeverity.WARNING,
            message=f"Potential duplicate: '{name1}' and '{name2}' ({similarity}% similar)",
            affected_nodes=[str(uuid4()), str(uuid4())],
            suggested_action="Merge entities",
            details={"entity1": name1, "entity2": name2, "similarity": similarity},
        )
