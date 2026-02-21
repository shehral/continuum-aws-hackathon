"""Tests for the dashboard router."""

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


class TestGetDashboardStats:
    """Tests for GET /stats endpoint."""

    @pytest.fixture
    def mock_postgres_session(self):
        """Create a mock PostgreSQL session."""
        session = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_get_dashboard_stats_success(self, mock_postgres_session):
        """Should return dashboard statistics."""
        mock_neo4j_session = create_neo4j_session_mock()

        # Mock PostgreSQL session count
        mock_pg_result = AsyncMock()
        mock_pg_result.scalar = MagicMock(return_value=15)
        mock_postgres_session.execute = AsyncMock(return_value=mock_pg_result)

        # Mock Neo4j queries - the router makes 3 queries:
        # 1. Count decisions
        # 2. Count entities
        # 3. Get recent decisions with entities
        recent_decisions = [
            {
                "d": {
                    "id": str(uuid4()),
                    "trigger": "Recent decision 1",
                    "context": "Context 1",
                    "options": ["A", "B"],
                    "decision": "Choice 1",
                    "rationale": "Reason 1",
                    "confidence": 0.9,
                    "created_at": "2024-01-15T00:00:00Z",
                },
                "entities": [
                    {"id": str(uuid4()), "name": "Entity1", "type": "technology"}
                ],
            },
            {
                "d": {
                    "id": str(uuid4()),
                    "trigger": "Recent decision 2",
                    "context": "Context 2",
                    "options": ["X", "Y"],
                    "decision": "Choice 2",
                    "rationale": "Reason 2",
                    "confidence": 0.8,
                    "created_at": "2024-01-14T00:00:00Z",
                },
                "entities": [],
            },
        ]

        call_count = [0]

        async def mock_neo4j_run(query, **params):
            call_count[0] += 1
            result = MagicMock()

            if "count(d)" in query.lower():
                # Decision count
                result.single = AsyncMock(return_value={"count": 25})
            elif "count(e)" in query.lower():
                # Entity count
                result.single = AsyncMock(return_value={"count": 50})
            else:
                # Recent decisions - return async iterator
                async def async_iter():
                    for r in recent_decisions:
                        yield r

                result.__aiter__ = lambda self: async_iter()

            return result

        mock_neo4j_session.run = mock_neo4j_run

        with (
            patch(
                "routers.dashboard.get_neo4j_session",
                new_callable=AsyncMock,
                return_value=mock_neo4j_session,
            ),
            patch(
                "routers.dashboard.get_db",
                return_value=mock_postgres_session,
            ),
        ):
            from routers.dashboard import get_dashboard_stats

            result = await get_dashboard_stats(db=mock_postgres_session)

            assert result.total_decisions == 25
            assert result.total_entities == 50
            assert result.total_sessions == 15
            assert len(result.recent_decisions) == 2

    @pytest.mark.asyncio
    async def test_get_dashboard_stats_empty(self, mock_postgres_session):
        """Should return zeros when database is empty."""
        mock_neo4j_session = create_neo4j_session_mock()

        # Mock PostgreSQL session count
        mock_pg_result = AsyncMock()
        mock_pg_result.scalar = MagicMock(return_value=0)
        mock_postgres_session.execute = AsyncMock(return_value=mock_pg_result)

        async def mock_neo4j_run(query, **params):
            result = MagicMock()

            if "count(d)" in query.lower():
                result.single = AsyncMock(return_value={"count": 0})
            elif "count(e)" in query.lower():
                result.single = AsyncMock(return_value={"count": 0})
            else:

                async def empty_iter():
                    return
                    yield

                result.__aiter__ = lambda self: empty_iter()

            return result

        mock_neo4j_session.run = mock_neo4j_run

        with patch(
            "routers.dashboard.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.dashboard import get_dashboard_stats

            result = await get_dashboard_stats(db=mock_postgres_session)

            assert result.total_decisions == 0
            assert result.total_entities == 0
            assert result.total_sessions == 0
            assert result.recent_decisions == []

    @pytest.mark.asyncio
    async def test_get_dashboard_stats_null_session_count(self, mock_postgres_session):
        """Should handle null session count gracefully."""
        mock_neo4j_session = create_neo4j_session_mock()

        # Mock PostgreSQL returning None
        mock_pg_result = AsyncMock()
        mock_pg_result.scalar = MagicMock(return_value=None)
        mock_postgres_session.execute = AsyncMock(return_value=mock_pg_result)

        async def mock_neo4j_run(query, **params):
            result = MagicMock()

            if "count(d)" in query.lower():
                result.single = AsyncMock(return_value={"count": 5})
            elif "count(e)" in query.lower():
                result.single = AsyncMock(return_value={"count": 10})
            else:

                async def empty_iter():
                    return
                    yield

                result.__aiter__ = lambda self: empty_iter()

            return result

        mock_neo4j_session.run = mock_neo4j_run

        with patch(
            "routers.dashboard.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.dashboard import get_dashboard_stats

            result = await get_dashboard_stats(db=mock_postgres_session)

            # Should default to 0 when None
            assert result.total_sessions == 0


class TestRecentDecisions:
    """Tests for recent decisions in dashboard stats."""

    @pytest.fixture
    def mock_postgres_session(self):
        """Create a mock PostgreSQL session."""
        session = AsyncMock()
        mock_pg_result = AsyncMock()
        mock_pg_result.scalar = MagicMock(return_value=0)
        session.execute = AsyncMock(return_value=mock_pg_result)
        return session

    @pytest.mark.asyncio
    async def test_recent_decisions_ordered_by_date(self, mock_postgres_session):
        """Recent decisions should be ordered by creation date."""
        mock_neo4j_session = create_neo4j_session_mock()

        recent_decisions = [
            {
                "d": {
                    "id": "1",
                    "trigger": "Newest",
                    "context": "Context",
                    "options": ["A"],
                    "decision": "A",
                    "rationale": "Reason",
                    "confidence": 0.9,
                    "created_at": "2024-01-20T00:00:00Z",
                },
                "entities": [],
            },
            {
                "d": {
                    "id": "2",
                    "trigger": "Older",
                    "context": "Context",
                    "options": ["B"],
                    "decision": "B",
                    "rationale": "Reason",
                    "confidence": 0.8,
                    "created_at": "2024-01-10T00:00:00Z",
                },
                "entities": [],
            },
        ]

        async def mock_run(query, **params):
            result = MagicMock()

            if "count(d)" in query.lower():
                result.single = AsyncMock(return_value={"count": 2})
            elif "count(e)" in query.lower():
                result.single = AsyncMock(return_value={"count": 0})
            else:

                async def async_iter():
                    for r in recent_decisions:
                        yield r

                result.__aiter__ = lambda self: async_iter()

            return result

        mock_neo4j_session.run = mock_run

        with patch(
            "routers.dashboard.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.dashboard import get_dashboard_stats

            result = await get_dashboard_stats(db=mock_postgres_session)

            assert len(result.recent_decisions) == 2
            # First should be the newest
            assert result.recent_decisions[0].trigger == "Newest"
