"""Contract Tests for Dashboard API.

QA-P2-2: Tests that /api/dashboard/stats responses match expected schema.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from tests.contract.schemas import DashboardStatsSchema, ErrorResponseSchema


class TestDashboardStatsContract:
    """Contract tests for GET /api/dashboard/stats endpoint."""

    @pytest.fixture
    def mock_neo4j_session(self):
        """Create a mock Neo4j session."""
        session = AsyncMock()

        # Mock decision count query
        decision_result = AsyncMock()
        decision_result.single = AsyncMock(return_value={"count": 10})

        # Mock entity count query
        entity_result = AsyncMock()
        entity_result.single = AsyncMock(return_value={"count": 25})

        # Mock recent decisions query
        recent_result = AsyncMock()
        recent_result.__aiter__ = lambda self: self._async_iter()

        async def _async_iter():
            decisions = [
                {
                    "d": {
                        "id": "test-id-1",
                        "trigger": "Choose database",
                        "context": "Building new app",
                        "options": ["PostgreSQL", "MySQL"],
                        "decision": "PostgreSQL",
                        "rationale": "Better features",
                        "confidence": 0.85,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "source": "manual",
                    },
                    "entities": [
                        {"id": "ent-1", "name": "PostgreSQL", "type": "technology"}
                    ],
                }
            ]
            for d in decisions:
                yield d

        recent_result._async_iter = _async_iter

        def mock_run(query, **kwargs):
            if "count(d)" in query:
                return decision_result
            elif "count(e)" in query:
                return entity_result
            else:
                return recent_result

        session.run = AsyncMock(side_effect=mock_run)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        return session

    @pytest.fixture
    def mock_postgres_session(self):
        """Create a mock PostgreSQL session."""
        session = MagicMock()
        result = MagicMock()
        result.scalar.return_value = 5  # Session count
        session.execute = AsyncMock(return_value=result)
        return session

    def test_response_matches_schema_structure(self):
        """Test that a valid response matches the schema structure."""
        # Sample valid response
        valid_response = {
            "total_decisions": 10,
            "total_entities": 25,
            "total_sessions": 5,
            "recent_decisions": [
                {
                    "id": "test-id-1",
                    "trigger": "Choose database",
                    "context": "Building new app",
                    "options": ["PostgreSQL", "MySQL"],
                    "decision": "PostgreSQL",
                    "rationale": "Better features",
                    "confidence": 0.85,
                    "created_at": "2026-01-30T12:00:00Z",
                    "entities": [
                        {"id": "ent-1", "name": "PostgreSQL", "type": "technology"}
                    ],
                    "source": "manual",
                }
            ],
        }

        # Should not raise
        schema = DashboardStatsSchema(**valid_response)
        assert schema.total_decisions == 10
        assert schema.total_entities == 25
        assert schema.total_sessions == 5
        assert len(schema.recent_decisions) == 1

    def test_response_requires_all_fields(self):
        """Test that missing required fields raise validation error."""
        incomplete_response = {
            "total_decisions": 10,
            # Missing total_entities, total_sessions, recent_decisions
        }

        with pytest.raises(ValidationError) as exc_info:
            DashboardStatsSchema(**incomplete_response)

        errors = exc_info.value.errors()
        field_names = [e["loc"][0] for e in errors]
        assert "total_entities" in field_names
        assert "total_sessions" in field_names
        assert "recent_decisions" in field_names

    def test_response_validates_counts_non_negative(self):
        """Test that negative counts are rejected."""
        invalid_response = {
            "total_decisions": -1,  # Invalid
            "total_entities": 25,
            "total_sessions": 5,
            "recent_decisions": [],
        }

        with pytest.raises(ValidationError):
            DashboardStatsSchema(**invalid_response)

    def test_decision_requires_valid_confidence(self):
        """Test that decision confidence must be between 0 and 1."""
        invalid_response = {
            "total_decisions": 1,
            "total_entities": 1,
            "total_sessions": 1,
            "recent_decisions": [
                {
                    "id": "test-id",
                    "trigger": "Test",
                    "context": "Test context",
                    "options": ["A"],
                    "decision": "A",
                    "rationale": "Because",
                    "confidence": 1.5,  # Invalid - > 1
                    "created_at": "2026-01-30T12:00:00Z",
                    "entities": [],
                }
            ],
        }

        with pytest.raises(ValidationError):
            DashboardStatsSchema(**invalid_response)

    def test_decision_entity_requires_name(self):
        """Test that entity name is required."""
        invalid_response = {
            "total_decisions": 1,
            "total_entities": 1,
            "total_sessions": 1,
            "recent_decisions": [
                {
                    "id": "test-id",
                    "trigger": "Test",
                    "context": "Test context",
                    "options": ["A"],
                    "decision": "A",
                    "rationale": "Because",
                    "confidence": 0.9,
                    "created_at": "2026-01-30T12:00:00Z",
                    "entities": [
                        {"id": "ent-1", "name": "", "type": "technology"}  # Empty name
                    ],
                }
            ],
        }

        with pytest.raises(ValidationError):
            DashboardStatsSchema(**invalid_response)

    def test_empty_recent_decisions_is_valid(self):
        """Test that empty recent_decisions list is valid."""
        valid_response = {
            "total_decisions": 0,
            "total_entities": 0,
            "total_sessions": 0,
            "recent_decisions": [],
        }

        schema = DashboardStatsSchema(**valid_response)
        assert schema.recent_decisions == []

    def test_error_response_matches_schema(self):
        """Test that error responses match expected schema."""
        error_response = {"detail": "Service unavailable"}

        schema = ErrorResponseSchema(**error_response)
        assert schema.detail == "Service unavailable"

    def test_error_response_requires_detail(self):
        """Test that error response requires detail field."""
        invalid_error = {"message": "Error"}  # Wrong field name

        with pytest.raises(ValidationError):
            ErrorResponseSchema(**invalid_error)
