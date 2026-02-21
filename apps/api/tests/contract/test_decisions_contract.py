"""Contract Tests for Decisions API.

QA-P2-2: Tests that /api/decisions responses match expected schema.
"""

import pytest
from pydantic import ValidationError

from tests.contract.schemas import (
    DecisionSchema,
    EntitySchema,
)


class TestDecisionsContract:
    """Contract tests for /api/decisions endpoints."""

    def test_decision_schema_valid(self):
        """Test that valid decision data passes schema validation."""
        valid_decision = {
            "id": "decision-123",
            "trigger": "Need to choose a database",
            "context": "Building a new web application",
            "options": ["PostgreSQL", "MySQL", "MongoDB"],
            "decision": "PostgreSQL",
            "rationale": "Best for relational data with ACID compliance",
            "confidence": 0.9,
            "created_at": "2026-01-30T12:00:00Z",
            "entities": [
                {"id": "ent-1", "name": "PostgreSQL", "type": "technology"},
                {"id": "ent-2", "name": "Database", "type": "concept"},
            ],
            "source": "manual",
        }

        schema = DecisionSchema(**valid_decision)
        assert schema.id == "decision-123"
        assert schema.confidence == 0.9
        assert len(schema.entities) == 2
        assert schema.source == "manual"

    def test_decision_schema_requires_id(self):
        """Test that decision id is required."""
        missing_id = {
            "trigger": "Need to choose",
            "context": "Context",
            "options": ["A"],
            "decision": "A",
            "rationale": "Reason",
            "confidence": 0.8,
            "created_at": "2026-01-30T12:00:00Z",
            "entities": [],
        }

        with pytest.raises(ValidationError) as exc_info:
            DecisionSchema(**missing_id)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("id",) for e in errors)

    def test_decision_schema_validates_confidence_range(self):
        """Test that confidence must be 0.0-1.0."""
        base_decision = {
            "id": "test-id",
            "trigger": "Test",
            "context": "Context",
            "options": ["A"],
            "decision": "A",
            "rationale": "Reason",
            "created_at": "2026-01-30T12:00:00Z",
            "entities": [],
        }

        # Test confidence > 1.0
        with pytest.raises(ValidationError):
            DecisionSchema(**{**base_decision, "confidence": 1.5})

        # Test confidence < 0.0
        with pytest.raises(ValidationError):
            DecisionSchema(**{**base_decision, "confidence": -0.1})

        # Test valid confidence at boundaries
        schema = DecisionSchema(**{**base_decision, "confidence": 0.0})
        assert schema.confidence == 0.0

        schema = DecisionSchema(**{**base_decision, "confidence": 1.0})
        assert schema.confidence == 1.0

    def test_decision_schema_requires_options_list(self):
        """Test that options must be a non-empty list."""
        missing_options = {
            "id": "test-id",
            "trigger": "Test",
            "context": "Context",
            "decision": "A",
            "rationale": "Reason",
            "confidence": 0.8,
            "created_at": "2026-01-30T12:00:00Z",
            "entities": [],
        }

        with pytest.raises(ValidationError) as exc_info:
            DecisionSchema(**missing_options)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("options",) for e in errors)

    def test_decision_schema_default_source(self):
        """Test that source defaults to unknown."""
        decision_without_source = {
            "id": "test-id",
            "trigger": "Test",
            "context": "Context",
            "options": ["A"],
            "decision": "A",
            "rationale": "Reason",
            "confidence": 0.8,
            "created_at": "2026-01-30T12:00:00Z",
            "entities": [],
        }

        schema = DecisionSchema(**decision_without_source)
        assert schema.source == "unknown"

    def test_decision_schema_valid_sources(self):
        """Test that valid source values are accepted."""
        base_decision = {
            "id": "test-id",
            "trigger": "Test",
            "context": "Context",
            "options": ["A"],
            "decision": "A",
            "rationale": "Reason",
            "confidence": 0.8,
            "created_at": "2026-01-30T12:00:00Z",
            "entities": [],
        }

        valid_sources = ["claude_logs", "interview", "manual", "unknown"]

        for source in valid_sources:
            schema = DecisionSchema(**{**base_decision, "source": source})
            assert schema.source == source

    def test_entity_schema_valid(self):
        """Test that valid entity data passes schema validation."""
        valid_entity = {
            "id": "entity-123",
            "name": "PostgreSQL",
            "type": "technology",
        }

        schema = EntitySchema(**valid_entity)
        assert schema.id == "entity-123"
        assert schema.name == "PostgreSQL"
        assert schema.type == "technology"

    def test_entity_schema_requires_name(self):
        """Test that entity name is required."""
        missing_name = {
            "id": "entity-123",
            "type": "technology",
        }

        with pytest.raises(ValidationError) as exc_info:
            EntitySchema(**missing_name)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) for e in errors)

    def test_entity_schema_requires_type(self):
        """Test that entity type is required."""
        missing_type = {
            "id": "entity-123",
            "name": "PostgreSQL",
        }

        with pytest.raises(ValidationError) as exc_info:
            EntitySchema(**missing_type)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("type",) for e in errors)

    def test_entity_schema_id_optional(self):
        """Test that entity id is optional (for creation)."""
        no_id = {
            "name": "PostgreSQL",
            "type": "technology",
        }

        schema = EntitySchema(**no_id)
        assert schema.id is None
        assert schema.name == "PostgreSQL"

    def test_entity_name_cannot_be_empty(self):
        """Test that entity name cannot be empty string."""
        empty_name = {
            "id": "entity-123",
            "name": "",
            "type": "technology",
        }

        with pytest.raises(ValidationError):
            EntitySchema(**empty_name)

    def test_decision_list_response(self):
        """Test that a list of decisions validates correctly."""
        decisions = [
            {
                "id": "decision-1",
                "trigger": "Choose database",
                "context": "Context 1",
                "options": ["A", "B"],
                "decision": "A",
                "rationale": "Reason 1",
                "confidence": 0.8,
                "created_at": "2026-01-30T12:00:00Z",
                "entities": [],
            },
            {
                "id": "decision-2",
                "trigger": "Choose framework",
                "context": "Context 2",
                "options": ["X", "Y"],
                "decision": "X",
                "rationale": "Reason 2",
                "confidence": 0.9,
                "created_at": "2026-01-30T12:01:00Z",
                "entities": [],
            },
        ]

        # Validate each decision
        for decision_data in decisions:
            schema = DecisionSchema(**decision_data)
            assert schema.id.startswith("decision-")

    def test_decision_with_multiple_entities(self):
        """Test decision with multiple related entities."""
        decision = {
            "id": "decision-123",
            "trigger": "Database and cache selection",
            "context": "Building high-performance API",
            "options": ["PostgreSQL + Redis", "MySQL + Memcached"],
            "decision": "PostgreSQL + Redis",
            "rationale": "Best combination for our use case",
            "confidence": 0.95,
            "created_at": "2026-01-30T12:00:00Z",
            "entities": [
                {"id": "ent-1", "name": "PostgreSQL", "type": "technology"},
                {"id": "ent-2", "name": "Redis", "type": "technology"},
                {"id": "ent-3", "name": "Caching", "type": "concept"},
                {"id": "ent-4", "name": "API Performance", "type": "concept"},
            ],
        }

        schema = DecisionSchema(**decision)
        assert len(schema.entities) == 4

        # Verify entity types
        entity_types = [e.type for e in schema.entities]
        assert entity_types.count("technology") == 2
        assert entity_types.count("concept") == 2

    def test_decision_datetime_parsing(self):
        """Test that various datetime formats are accepted."""
        base_decision = {
            "id": "test-id",
            "trigger": "Test",
            "context": "Context",
            "options": ["A"],
            "decision": "A",
            "rationale": "Reason",
            "confidence": 0.8,
            "entities": [],
        }

        valid_datetime_formats = [
            "2026-01-30T12:00:00Z",
            "2026-01-30T12:00:00+00:00",
            "2026-01-30T12:00:00.000Z",
            "2026-01-30 12:00:00",
        ]

        for dt_str in valid_datetime_formats:
            schema = DecisionSchema(**{**base_decision, "created_at": dt_str})
            assert schema.created_at is not None
