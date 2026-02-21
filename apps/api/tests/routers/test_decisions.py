"""Tests for the decisions router."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def create_async_result_mock(records):
    """Create a mock Neo4j result that works as an async iterator."""
    result = MagicMock()

    async def async_iter():
        for r in records:
            yield r

    result.__aiter__ = lambda self: async_iter()
    return result


def create_neo4j_session_mock():
    """Create a mock Neo4j session that works as an async context manager."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


class TestGetDecisions:
    """Tests for GET / endpoint."""

    @pytest.fixture
    def sample_decisions(self):
        """Sample decision records."""
        return [
            {
                "d": {
                    "id": str(uuid4()),
                    "trigger": "Choosing a database",
                    "context": "Need relational database",
                    "options": ["PostgreSQL", "MySQL"],
                    "decision": "PostgreSQL",
                    "rationale": "Better for complex queries",
                    "confidence": 0.9,
                    "created_at": "2024-01-01T00:00:00Z",
                    "source": "manual",
                },
                "entities": [
                    {"id": str(uuid4()), "name": "PostgreSQL", "type": "technology"}
                ],
            },
            {
                "d": {
                    "id": str(uuid4()),
                    "trigger": "Selecting caching",
                    "context": "Need fast cache",
                    "options": ["Redis", "Memcached"],
                    "decision": "Redis",
                    "rationale": "Better data structures",
                    "confidence": 0.85,
                    "created_at": "2024-01-02T00:00:00Z",
                    "source": "interview",
                },
                "entities": [],
            },
        ]

    @pytest.mark.asyncio
    async def test_get_decisions_returns_list(self, sample_decisions):
        """Should return a list of decisions."""
        mock_session = create_neo4j_session_mock()
        mock_session.run = AsyncMock(
            return_value=create_async_result_mock(sample_decisions)
        )

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.decisions import get_decisions

            results = await get_decisions(limit=50, offset=0)
            assert len(results) == 2
            assert results[0].trigger == "Choosing a database"

    @pytest.mark.asyncio
    async def test_get_decisions_empty(self):
        """Should return empty list when no decisions."""
        mock_session = create_neo4j_session_mock()
        mock_session.run = AsyncMock(return_value=create_async_result_mock([]))

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.decisions import get_decisions

            results = await get_decisions(limit=50, offset=0)
            assert results == []

    @pytest.mark.asyncio
    async def test_get_decisions_with_pagination(self):
        """Should pass pagination parameters to query."""
        mock_session = create_neo4j_session_mock()
        mock_session.run = AsyncMock(return_value=create_async_result_mock([]))

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.decisions import get_decisions

            await get_decisions(limit=10, offset=20)

            # Verify query was called with pagination params
            call_args = mock_session.run.call_args
            assert call_args[1]["limit"] == 10
            assert call_args[1]["offset"] == 20


class TestGetDecision:
    """Tests for GET /{decision_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_decision_found(self):
        """Should return decision when found."""
        mock_session = create_neo4j_session_mock()
        decision_id = str(uuid4())
        decision_data = {
            "d": {
                "id": decision_id,
                "trigger": "Test decision",
                "context": "Test context",
                "options": ["A", "B"],
                "decision": "A",
                "rationale": "Because",
                "confidence": 0.9,
                "created_at": "2024-01-01T00:00:00Z",
                "source": "manual",
            },
            "entities": [],
        }

        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=decision_data)
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.decisions import get_decision

            result = await get_decision(decision_id)
            assert result.id == decision_id
            assert result.trigger == "Test decision"

    @pytest.mark.asyncio
    async def test_get_decision_not_found(self):
        """Should raise 404 when decision not found."""
        mock_session = create_neo4j_session_mock()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from fastapi import HTTPException

            from routers.decisions import get_decision

            with pytest.raises(HTTPException) as exc_info:
                await get_decision("nonexistent-id")
            assert exc_info.value.status_code == 404


class TestDeleteDecision:
    """Tests for DELETE /{decision_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_decision_success(self):
        """Should delete decision when it exists."""
        mock_session = create_neo4j_session_mock()
        decision_id = str(uuid4())
        decision_data = {"d": {"id": decision_id}}

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            result = AsyncMock()
            if call_count[0] == 1:
                result.single = AsyncMock(return_value=decision_data)
            else:
                result.single = AsyncMock(return_value=None)
            return result

        mock_session.run = mock_run

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.decisions import delete_decision

            result = await delete_decision(decision_id)
            assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_decision_not_found(self):
        """Should raise 404 when decision doesn't exist."""
        mock_session = create_neo4j_session_mock()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from fastapi import HTTPException

            from routers.decisions import delete_decision

            with pytest.raises(HTTPException) as exc_info:
                await delete_decision("nonexistent-id")
            assert exc_info.value.status_code == 404


class TestCreateDecision:
    """Tests for POST / endpoint."""

    @pytest.mark.asyncio
    async def test_create_decision_manual(self):
        """Should create decision without auto-extraction."""
        mock_session = create_neo4j_session_mock()
        decision_id = str(uuid4())

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            result = AsyncMock()
            if "RETURN d, entities" in query:
                result.single = AsyncMock(
                    return_value={
                        "d": {
                            "id": decision_id,
                            "trigger": "Test",
                            "context": "Context",
                            "options": ["A"],
                            "decision": "A",
                            "rationale": "Because",
                            "confidence": 1.0,
                            "created_at": "2024-01-01T00:00:00Z",
                            "source": "manual",
                        },
                        "entities": [],
                    }
                )
            else:
                result.single = AsyncMock(return_value=None)
            return result

        mock_session.run = mock_run

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.decisions import ManualDecisionInput, create_decision

            input_data = ManualDecisionInput(
                trigger="Test",
                context="Context",
                options=["A"],
                decision="A",
                rationale="Because",
                auto_extract=False,
            )
            result = await create_decision(input_data)
            assert result.trigger == "Test"
            assert result.source == "manual"


class TestUpdateDecision:
    """Tests for PUT /{decision_id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_decision_success(self):
        """Should update decision when it exists."""
        mock_session = create_neo4j_session_mock()
        decision_id = str(uuid4())
        original_data = {
            "d": {
                "id": decision_id,
                "trigger": "Original trigger",
                "context": "Original context",
                "options": ["A", "B"],
                "decision": "A",
                "rationale": "Original reason",
                "confidence": 0.9,
                "created_at": "2024-01-01T00:00:00Z",
                "source": "manual",
            }
        }
        updated_data = {
            "d": {
                "id": decision_id,
                "trigger": "Updated trigger",
                "context": "Original context",
                "options": ["A", "B"],
                "decision": "A",
                "rationale": "Original reason",
                "confidence": 0.9,
                "created_at": "2024-01-01T00:00:00Z",
                "edited_at": "2024-01-02T00:00:00Z",
                "edit_count": 1,
                "source": "manual",
            },
            "entities": [],
        }

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            result = AsyncMock()
            if call_count[0] == 1:
                # First call: check if decision exists
                result.single = AsyncMock(return_value=original_data)
            elif call_count[0] == 2:
                # Second call: update
                result.single = AsyncMock(return_value=None)
            else:
                # Third call: fetch updated decision
                result.single = AsyncMock(return_value=updated_data)
            return result

        mock_session.run = mock_run

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from models.schemas import DecisionUpdate
            from routers.decisions import update_decision

            update_data = DecisionUpdate(trigger="Updated trigger")
            result = await update_decision(decision_id, update_data)
            assert result.trigger == "Updated trigger"
            assert result.id == decision_id

    @pytest.mark.asyncio
    async def test_update_decision_not_found(self):
        """Should raise 404 when decision doesn't exist."""
        mock_session = create_neo4j_session_mock()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from fastapi import HTTPException

            from models.schemas import DecisionUpdate
            from routers.decisions import update_decision

            with pytest.raises(HTTPException) as exc_info:
                await update_decision(
                    "nonexistent-id",
                    DecisionUpdate(trigger="New trigger"),
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_decision_no_fields(self):
        """Should raise 400 when no fields provided."""
        mock_session = create_neo4j_session_mock()
        decision_id = str(uuid4())
        decision_data = {"d": {"id": decision_id}}
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=decision_data)
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from fastapi import HTTPException

            from models.schemas import DecisionUpdate
            from routers.decisions import update_decision

            with pytest.raises(HTTPException) as exc_info:
                await update_decision(decision_id, DecisionUpdate())
            assert exc_info.value.status_code == 400
            assert "No fields to update" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_update_decision_multiple_fields(self):
        """Should update multiple fields at once."""
        mock_session = create_neo4j_session_mock()
        decision_id = str(uuid4())
        original_data = {"d": {"id": decision_id}}
        updated_data = {
            "d": {
                "id": decision_id,
                "trigger": "New trigger",
                "context": "New context",
                "options": ["X", "Y"],
                "decision": "X",
                "rationale": "New reason",
                "confidence": 0.9,
                "created_at": "2024-01-01T00:00:00Z",
                "edited_at": "2024-01-02T00:00:00Z",
                "edit_count": 1,
                "source": "manual",
            },
            "entities": [],
        }

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            result = AsyncMock()
            if call_count[0] == 1:
                result.single = AsyncMock(return_value=original_data)
            elif call_count[0] == 2:
                result.single = AsyncMock(return_value=None)
            else:
                result.single = AsyncMock(return_value=updated_data)
            return result

        mock_session.run = mock_run

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from models.schemas import DecisionUpdate
            from routers.decisions import update_decision

            update_data = DecisionUpdate(
                trigger="New trigger",
                context="New context",
                rationale="New reason",
            )
            result = await update_decision(decision_id, update_data)
            assert result.trigger == "New trigger"
            assert result.context == "New context"
            assert result.rationale == "New reason"
