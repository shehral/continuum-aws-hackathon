"""Tests for the search router."""

from unittest.mock import AsyncMock, MagicMock, patch

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


class TestSearchEndpoint:
    """Tests for GET / (search) endpoint."""

    @pytest.mark.asyncio
    async def test_search_returns_decision_results(self):
        """Search should return matching decisions."""
        mock_session = create_neo4j_session_mock()

        sample_decisions = [
            {
                "d": {
                    "id": "decision-1",
                    "trigger": "Choosing a database",
                    "decision": "Use PostgreSQL",
                    "confidence": 0.9,
                },
                "score": 0.95,
            }
        ]

        # First call returns sample_decisions, subsequent calls return empty
        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            if call_count[0] == 1:
                return create_async_result_mock(sample_decisions)
            return create_async_result_mock([])

        mock_session.run = mock_run

        with patch(
            "routers.search.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.search import search

            results = await search(query="database", type="decision")

            assert len(results) >= 1
            assert results[0].type == "decision"

    @pytest.mark.asyncio
    async def test_search_returns_entity_results(self):
        """Search should return matching entities."""
        mock_session = create_neo4j_session_mock()

        sample_entities = [
            {
                "e": {
                    "id": "entity-1",
                    "name": "PostgreSQL",
                    "type": "technology",
                },
                "score": 0.9,
            }
        ]

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            # Return empty for decision queries, entities for entity queries
            if "Entity" in query:
                return create_async_result_mock(sample_entities)
            return create_async_result_mock([])

        mock_session.run = mock_run

        with patch(
            "routers.search.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.search import search

            results = await search(query="postgres", type="entity")

            assert len(results) >= 1
            assert results[0].type == "entity"

    @pytest.mark.asyncio
    async def test_search_empty_results(self):
        """Search should return empty list when no matches."""
        mock_session = create_neo4j_session_mock()
        mock_session.run = AsyncMock(return_value=create_async_result_mock([]))

        with patch(
            "routers.search.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.search import search

            results = await search(query="xyz123", type="decision")

            assert results == []


class TestSuggestEndpoint:
    """Tests for GET /suggest endpoint."""

    @pytest.mark.asyncio
    async def test_suggest_returns_matching_entities(self):
        """Suggest should return entities matching the prefix."""
        mock_session = create_neo4j_session_mock()

        entity_suggestions = [
            {"id": "e1", "name": "PostgreSQL", "type": "technology"},
            {"id": "e2", "name": "Postgres Config", "type": "concept"},
        ]

        decision_suggestions = []

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            if call_count[0] == 1:
                return create_async_result_mock(entity_suggestions)
            return create_async_result_mock(decision_suggestions)

        mock_session.run = mock_run

        with patch(
            "routers.search.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.search import search_suggestions

            results = await search_suggestions(query="post", limit=10)

            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_suggest_respects_limit(self):
        """Suggest should respect the limit parameter."""
        mock_session = create_neo4j_session_mock()

        entity_suggestions = [
            {"id": "e1", "name": "Item1", "type": "concept"},
            {"id": "e2", "name": "Item2", "type": "concept"},
            {"id": "e3", "name": "Item3", "type": "concept"},
        ]

        decision_suggestions = [
            {"id": "d1", "trigger": "Decision about Item"},
        ]

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            # First call is entities, second is decisions
            if call_count[0] == 1:
                return create_async_result_mock(entity_suggestions)
            return create_async_result_mock(decision_suggestions)

        mock_session.run = mock_run

        with patch(
            "routers.search.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.search import search_suggestions

            # Limit is applied in the function's return statement
            results = await search_suggestions(query="item", limit=2)

            # The function returns results[:limit]
            assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_suggest_empty_results(self):
        """Suggest should return empty list when no matches."""
        mock_session = create_neo4j_session_mock()
        mock_session.run = AsyncMock(return_value=create_async_result_mock([]))

        with patch(
            "routers.search.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.search import search_suggestions

            results = await search_suggestions(query="xyz", limit=10)

            assert results == []
