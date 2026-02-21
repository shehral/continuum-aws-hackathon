"""Tests for the graph router."""

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


class TestGetGraph:
    """Tests for GET / endpoint (paginated)."""

    @pytest.fixture
    def sample_decisions(self):
        """Sample decision nodes."""
        return [
            {
                "d": {
                    "id": str(uuid4()),
                    "trigger": "Choosing database",
                    "context": "Need fast queries",
                    "options": ["PostgreSQL", "MySQL"],
                    "decision": "PostgreSQL",
                    "rationale": "Better performance",
                    "confidence": 0.9,
                    "created_at": "2024-01-01T00:00:00Z",
                    "source": "manual",
                },
                "has_embedding": True,
            }
        ]

    @pytest.fixture
    def sample_entities(self):
        """Sample entity nodes."""
        return [
            {
                "e": {
                    "id": str(uuid4()),
                    "name": "PostgreSQL",
                    "type": "technology",
                    "aliases": [],
                },
                "has_embedding": True,
            }
        ]

    @pytest.fixture
    def sample_edges(self):
        """Sample graph edges."""
        return [
            {
                "source": "decision-1",
                "target": "entity-1",
                "relationship": "INVOLVES",
                "weight": 1.0,
                "score": None,
                "confidence": None,
                "shared_entities": None,
                "reasoning": None,
            }
        ]

    @pytest.mark.asyncio
    async def test_get_graph_returns_nodes_and_edges(
        self, sample_decisions, sample_entities, sample_edges
    ):
        """Should return paginated graph with nodes, edges, and pagination metadata."""
        mock_session = create_neo4j_session_mock()

        # Track the decision ID to use in edge matching
        decision_id = sample_decisions[0]["d"]["id"]
        entity_id = sample_entities[0]["e"]["id"]

        # Update edges to use actual IDs
        sample_edges[0]["source"] = decision_id
        sample_edges[0]["target"] = entity_id

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            result = MagicMock()
            # Count query returns total
            if "count(d) as total" in query:
                result.single = AsyncMock(return_value={"total": 1})
                return result
            # Decision query with pagination
            elif "DecisionTrace" in query and "SKIP" in query and "LIMIT" in query:
                return create_async_result_mock(sample_decisions)
            # Entity query
            elif (
                "INVOLVES" in query
                and "e:Entity" in query
                and "(a)-[r]->(b)" not in query
            ):
                return create_async_result_mock(sample_entities)
            # Relationship query
            elif "(a)-[r]->(b)" in query or "a.id as source" in query:
                return create_async_result_mock(sample_edges)
            else:
                return create_async_result_mock([])

        mock_session.run = mock_run

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_graph

            result = await get_graph(page=1, page_size=100, user_id="test-user")

            # Check pagination metadata
            assert result.pagination.page == 1
            assert result.pagination.page_size == 100
            assert result.pagination.total_count == 1
            assert result.pagination.has_more is False

            # Check nodes and edges
            assert len(result.nodes) >= 1
            assert isinstance(result.edges, list)

    @pytest.mark.asyncio
    async def test_get_graph_empty(self):
        """Should return empty paginated graph when database is empty."""
        mock_session = create_neo4j_session_mock()

        async def mock_run(query, **params):
            result = MagicMock()
            if "count(d) as total" in query:
                result.single = AsyncMock(return_value={"total": 0})
                return result
            return create_async_result_mock([])

        mock_session.run = mock_run

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_graph

            result = await get_graph(page=1, page_size=100, user_id="test-user")

            assert result.nodes == []
            assert result.edges == []
            assert result.pagination.total_count == 0
            assert result.pagination.has_more is False

    @pytest.mark.asyncio
    async def test_get_graph_filters_by_source(
        self, sample_decisions, sample_entities, sample_edges
    ):
        """Should filter by source when specified."""
        mock_session = create_neo4j_session_mock()

        decision_id = sample_decisions[0]["d"]["id"]
        entity_id = sample_entities[0]["e"]["id"]
        sample_edges[0]["source"] = decision_id
        sample_edges[0]["target"] = entity_id

        queries_called = []

        async def mock_run(query, **params):
            queries_called.append(query)
            result = MagicMock()
            if "count(d) as total" in query:
                result.single = AsyncMock(return_value={"total": 1})
                return result
            elif "DecisionTrace" in query and "SKIP" in query:
                return create_async_result_mock(sample_decisions)
            elif "INVOLVES" in query and "e:Entity" in query:
                return create_async_result_mock(sample_entities)
            elif "(a)-[r]->(b)" in query:
                return create_async_result_mock(sample_edges)
            else:
                return create_async_result_mock([])

        mock_session.run = mock_run

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_graph

            await get_graph(
                page=1, page_size=100, source_filter="manual", user_id="test-user"
            )

            # Verify at least one query includes source filter
            assert any("source" in q.lower() for q in queries_called)

    @pytest.mark.asyncio
    async def test_get_graph_pagination_metadata(self):
        """Should return correct pagination metadata for multiple pages."""
        mock_session = create_neo4j_session_mock()

        async def mock_run(query, **params):
            result = MagicMock()
            if "count(d) as total" in query:
                result.single = AsyncMock(return_value={"total": 250})
                return result
            return create_async_result_mock([])

        mock_session.run = mock_run

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_graph

            result = await get_graph(page=1, page_size=100, user_id="test-user")

            assert result.pagination.total_count == 250
            assert result.pagination.total_pages == 3
            assert result.pagination.has_more is True

            # Test last page
            result2 = await get_graph(page=3, page_size=100, user_id="test-user")
            assert result2.pagination.has_more is False


class TestGetFullGraph:
    """Tests for GET /all endpoint (unpaginated)."""

    @pytest.fixture
    def sample_decisions(self):
        """Sample decision nodes."""
        return [
            {
                "d": {
                    "id": str(uuid4()),
                    "trigger": "Choosing database",
                    "context": "Need fast queries",
                    "options": ["PostgreSQL", "MySQL"],
                    "decision": "PostgreSQL",
                    "rationale": "Better performance",
                    "confidence": 0.9,
                    "created_at": "2024-01-01T00:00:00Z",
                    "source": "manual",
                },
                "has_embedding": True,
            }
        ]

    @pytest.mark.asyncio
    async def test_get_full_graph_returns_unpaginated(self, sample_decisions):
        """Should return full graph without pagination."""
        mock_session = create_neo4j_session_mock()

        async def mock_run(query, **params):
            if "DecisionTrace" in query and "INVOLVES" not in query:
                return create_async_result_mock(sample_decisions)
            return create_async_result_mock([])

        mock_session.run = mock_run

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_full_graph

            result = await get_full_graph(user_id="test-user")

            # Should return GraphData (no pagination field)
            assert hasattr(result, "nodes")
            assert hasattr(result, "edges")
            assert not hasattr(result, "pagination")


class TestGetNodeNeighbors:
    """Tests for GET /nodes/{node_id}/neighbors endpoint."""

    @pytest.mark.asyncio
    async def test_get_node_neighbors_not_found(self):
        """Should return 404 when node not found."""
        mock_session = create_neo4j_session_mock()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from fastapi import HTTPException

            from routers.graph import get_node_neighbors

            with pytest.raises(HTTPException) as exc_info:
                await get_node_neighbors(
                    node_id="nonexistent-id",
                    limit=50,
                    relationship_types=None,
                    user_id="test-user",
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_node_neighbors_returns_neighbors(self):
        """Should return neighbors for a valid node."""
        mock_session = create_neo4j_session_mock()
        node_id = str(uuid4())

        neighbor_data = {
            "target": {
                "id": str(uuid4()),
                "name": "PostgreSQL",
                "type": "technology",
                "aliases": [],
            },
            "relationship": "INVOLVES",
            "weight": 1.0,
            "score": None,
            "confidence": None,
            "target_type": "Entity",
            "has_embedding": True,
        }

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            result = MagicMock()
            # Verify query
            if "labels(n)" in query:
                result.single = AsyncMock(return_value={"node_type": "DecisionTrace"})
                return result
            # Outgoing neighbors
            elif "source.id = $node_id" in query:
                return create_async_result_mock([neighbor_data])
            # Incoming neighbors
            elif "target.id = $node_id" in query:
                return create_async_result_mock([])
            return create_async_result_mock([])

        mock_session.run = mock_run

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_node_neighbors

            result = await get_node_neighbors(
                node_id=node_id, limit=50, relationship_types=None, user_id="test-user"
            )

            assert result.source_node_id == node_id
            assert len(result.neighbors) == 1
            assert result.neighbors[0].relationship == "INVOLVES"
            assert result.neighbors[0].direction == "outgoing"

    @pytest.mark.asyncio
    async def test_get_node_neighbors_with_relationship_filter(self):
        """Should filter neighbors by relationship type."""
        mock_session = create_neo4j_session_mock()
        node_id = str(uuid4())

        queries_called = []

        async def mock_run(query, **params):
            queries_called.append((query, params))
            result = MagicMock()
            if "labels(n)" in query:
                result.single = AsyncMock(return_value={"node_type": "DecisionTrace"})
                return result
            return create_async_result_mock([])

        mock_session.run = mock_run

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_node_neighbors

            await get_node_neighbors(
                node_id=node_id,
                limit=50,
                relationship_types="INVOLVES,SIMILAR_TO",
                user_id="test-user",
            )

            # Check that rel_types parameter was passed
            rel_types_passed = any(
                "rel_types" in params
                and params["rel_types"] == ["INVOLVES", "SIMILAR_TO"]
                for _, params in queries_called
            )
            assert rel_types_passed


class TestGetNodeDetails:
    """Tests for GET /nodes/{node_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_decision_node(self):
        """Should return decision node details."""
        mock_session = create_neo4j_session_mock()
        node_id = str(uuid4())
        decision_data = {
            "d": {
                "id": node_id,
                "trigger": "Test decision",
                "context": "Test context",
                "options": ["A", "B"],
                "decision": "A",
                "rationale": "Because",
                "confidence": 0.9,
                "created_at": "2024-01-01T00:00:00Z",
            },
            "entities": ["PostgreSQL"],
            "supersedes": [],
            "conflicts_with": [],
            "has_embedding": True,
        }

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
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_node_details

            result = await get_node_details(node_id, user_id="test-user")

            assert result.id == node_id
            assert result.type == "decision"

    @pytest.mark.asyncio
    async def test_get_entity_node(self):
        """Should return entity node details."""
        mock_session = create_neo4j_session_mock()
        node_id = str(uuid4())
        entity_data = {
            "e": {
                "id": node_id,
                "name": "PostgreSQL",
                "type": "technology",
                "aliases": ["postgres", "pg"],
            },
            "decisions": ["Choosing a database"],
            "related_entities": [],
            "has_embedding": True,
        }

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            result = AsyncMock()
            if call_count[0] == 1:
                # First query for decision fails
                result.single = AsyncMock(return_value=None)
            else:
                # Second query for entity succeeds
                result.single = AsyncMock(return_value=entity_data)
            return result

        mock_session.run = mock_run

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_node_details

            result = await get_node_details(node_id, user_id="test-user")

            assert result.id == node_id
            assert result.type == "entity"

    @pytest.mark.asyncio
    async def test_get_node_not_found(self):
        """Should raise 404 when node not found."""
        mock_session = create_neo4j_session_mock()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from fastapi import HTTPException

            from routers.graph import get_node_details

            with pytest.raises(HTTPException) as exc_info:
                await get_node_details("nonexistent-id", user_id="test-user")
            assert exc_info.value.status_code == 404


class TestResetGraph:
    """Tests for DELETE /reset endpoint."""

    @pytest.mark.asyncio
    async def test_reset_requires_confirmation(self):
        """Should abort without confirmation."""
        mock_session = create_neo4j_session_mock()

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import reset_graph

            result = await reset_graph(confirm=False, user_id="test-user")

            assert result["status"] == "aborted"
            # Should not have called any Neo4j operations
            assert mock_session.run.call_count == 0

    @pytest.mark.asyncio
    async def test_reset_with_confirmation(self):
        """Should delete all data with confirmation."""
        mock_session = create_neo4j_session_mock()
        mock_session.run = AsyncMock()

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import reset_graph

            result = await reset_graph(confirm=True, user_id="test-user")

            assert result["status"] == "completed"
            # Should have called delete for user decisions and orphan cleanup
            assert mock_session.run.call_count == 2


class TestGetGraphStats:
    """Tests for GET /stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_stats_success(self):
        """Should return graph statistics."""
        mock_session = create_neo4j_session_mock()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(
            return_value={
                "total_decisions": 25,
                "decisions_with_embeddings": 20,
                "total_entities": 50,
                "entities_with_embeddings": 45,
                "total_relationships": 100,
            }
        )
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_graph_stats

            result = await get_graph_stats(user_id="test-user")

            assert result["decisions"]["total"] == 25
            assert result["decisions"]["with_embeddings"] == 20
            assert result["entities"]["total"] == 50
            assert result["relationships"] == 100

    @pytest.mark.asyncio
    async def test_get_stats_empty(self):
        """Should return zeros when database is empty."""
        mock_session = create_neo4j_session_mock()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_graph_stats

            result = await get_graph_stats(user_id="test-user")

            assert result["decisions"]["total"] == 0
            assert result["entities"]["total"] == 0
            assert result["relationships"] == 0
