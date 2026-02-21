"""Integration tests for Phase 3 features.

This test suite covers the following Phase 3 features:

P0-1: Semantic/Hybrid Search
- POST /api/graph/search/hybrid endpoint
- Combines lexical (fulltext) and semantic (vector) search
- Returns combined scores with score breakdown

P0-2: Decision Filtering
- Frontend filtering by source and confidence (URL params)
- Filters on GET /api/graph endpoint

P0-3: Decision Edit
- PUT /api/decisions/{id} endpoint with edit history tracking
- Tracks edited_at timestamp and edit_count

SD-003: Graph Pagination
- GET /api/graph with page/page_size params
- GET /api/graph/nodes/{id}/neighbors for lazy loading
- Returns PaginationMeta with total_count, total_pages, has_more

P1-3: Related Decisions Sidebar
- GET /api/graph/nodes/{id}/similar
- Returns similar decisions with similarity scores
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ============================================================================
# Test Helpers
# ============================================================================


def create_async_result_mock(records):
    """Create a mock Neo4j result that works as an async iterator."""
    result = MagicMock()

    async def async_iter():
        for r in records:
            yield r

    result.__aiter__ = lambda self: async_iter()
    result.single = AsyncMock(return_value=records[0] if records else None)
    return result


def create_neo4j_session_mock():
    """Create a mock Neo4j session that works as an async context manager."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


def make_decision_record(
    decision_id=None,
    trigger="Test trigger",
    source="manual",
    confidence=0.9,
    has_embedding=True,
    user_id="test-user",
):
    """Create a valid decision record dict for testing."""
    return {
        "d": {
            "id": decision_id or str(uuid4()),
            "trigger": trigger,
            "context": "Test context",
            "options": ["Option A", "Option B"],
            "decision": "Option A",
            "rationale": "Test rationale",
            "confidence": confidence,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "user_id": user_id,
        },
        "has_embedding": has_embedding,
    }


def make_entity_record(entity_id=None, name="TestEntity", entity_type="technology"):
    """Create a valid entity record dict for testing."""
    return {
        "e": {
            "id": entity_id or str(uuid4()),
            "name": name,
            "type": entity_type,
            "aliases": [],
        },
        "has_embedding": True,
    }


# ============================================================================
# P0-1: Hybrid Search Tests
# ============================================================================


class TestHybridSearch:
    """Tests for POST /api/graph/search/hybrid endpoint."""

    @pytest.fixture
    def mock_embedding_service(self):
        """Create a mock embedding service."""
        service = AsyncMock()
        service.embed_text = AsyncMock(return_value=[0.1] * 2048)
        return service

    @pytest.mark.asyncio
    async def test_hybrid_search_returns_combined_scores(self, mock_embedding_service):
        """Should return results with lexical, semantic, and combined scores."""
        mock_session = create_neo4j_session_mock()

        decision_id = str(uuid4())
        lexical_results = [
            {
                "id": decision_id,
                "type": "decision",
                "trigger": "Database selection",
                "decision": "PostgreSQL",
                "context": "Need fast queries",
                "rationale": "Better performance",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source": "manual",
                "fulltext_score": 5.0,
            }
        ]

        semantic_results = [
            {
                "id": decision_id,
                "type": "decision",
                "trigger": "Database selection",
                "decision": "PostgreSQL",
                "context": "Need fast queries",
                "rationale": "Better performance",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source": "manual",
                "semantic_score": 0.85,
            }
        ]

        async def mock_run(cypher, **params):
            if (
                "db.index.fulltext.queryNodes" in cypher
                and "decision_fulltext" in cypher
            ):
                return create_async_result_mock(lexical_results)
            elif (
                "db.index.fulltext.queryNodes" in cypher and "entity_fulltext" in cypher
            ):
                return create_async_result_mock([])
            elif (
                "db.index.vector.queryNodes" in cypher
                and "decision_embedding" in cypher
            ):
                return create_async_result_mock(semantic_results)
            elif (
                "db.index.vector.queryNodes" in cypher and "entity_embedding" in cypher
            ):
                return create_async_result_mock([])
            else:
                return create_async_result_mock([])

        mock_session.run = mock_run

        with (
            patch(
                "routers.graph.get_neo4j_session",
                new_callable=AsyncMock,
                return_value=mock_session,
            ),
            patch(
                "routers.graph.get_embedding_service",
                return_value=mock_embedding_service,
            ),
        ):
            from models.schemas import HybridSearchRequest
            from routers.graph import hybrid_search

            request = HybridSearchRequest(
                query="database",
                top_k=10,
                threshold=0.3,
                alpha=0.3,
                search_decisions=True,
                search_entities=False,
            )

            results = await hybrid_search(request, user_id="test-user")

            assert len(results) >= 1
            result = results[0]
            assert result.id == decision_id
            assert result.type == "decision"
            assert hasattr(result, "lexical_score")
            assert hasattr(result, "semantic_score")
            assert hasattr(result, "combined_score")

    @pytest.mark.asyncio
    async def test_hybrid_search_threshold_filtering(self, mock_embedding_service):
        """Should filter results below threshold."""
        mock_session = create_neo4j_session_mock()

        low_score_result = [
            {
                "id": str(uuid4()),
                "type": "decision",
                "trigger": "Low relevance",
                "decision": "Something",
                "context": "Context",
                "rationale": "Rationale",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source": "manual",
                "fulltext_score": 0.5,
            }
        ]

        async def mock_run(cypher, **params):
            if "fulltext" in cypher:
                return create_async_result_mock(low_score_result)
            return create_async_result_mock([])

        mock_session.run = mock_run

        with (
            patch(
                "routers.graph.get_neo4j_session",
                new_callable=AsyncMock,
                return_value=mock_session,
            ),
            patch(
                "routers.graph.get_embedding_service",
                return_value=mock_embedding_service,
            ),
        ):
            from models.schemas import HybridSearchRequest
            from routers.graph import hybrid_search

            request = HybridSearchRequest(
                query="database",
                top_k=10,
                threshold=0.8,
                alpha=0.3,
                search_decisions=True,
                search_entities=False,
            )

            results = await hybrid_search(request, user_id="test-user")
            assert all(r.combined_score >= 0.8 for r in results)

    @pytest.mark.asyncio
    async def test_hybrid_search_entities(self, mock_embedding_service):
        """Should search entities when requested."""
        mock_session = create_neo4j_session_mock()

        entity_results = [
            {
                "id": str(uuid4()),
                "type": "entity",
                "name": "PostgreSQL",
                "entity_type": "technology",
                "aliases": ["postgres", "pg"],
                "fulltext_score": 8.0,
            }
        ]

        async def mock_run(cypher, **params):
            if "entity_fulltext" in cypher:
                return create_async_result_mock(entity_results)
            return create_async_result_mock([])

        mock_session.run = mock_run

        with (
            patch(
                "routers.graph.get_neo4j_session",
                new_callable=AsyncMock,
                return_value=mock_session,
            ),
            patch(
                "routers.graph.get_embedding_service",
                return_value=mock_embedding_service,
            ),
        ):
            from models.schemas import HybridSearchRequest
            from routers.graph import hybrid_search

            request = HybridSearchRequest(
                query="postgres",
                top_k=10,
                threshold=0.0,
                alpha=0.3,
                search_decisions=False,
                search_entities=True,
            )

            results = await hybrid_search(request, user_id="test-user")
            assert any(r.type == "entity" for r in results)


# ============================================================================
# P0-2: Decision Filtering Tests
# ============================================================================


class TestDecisionFiltering:
    """Tests for decision filtering by source and confidence."""

    @pytest.mark.asyncio
    async def test_filter_by_source(self):
        """Should filter decisions by source type."""
        mock_session = create_neo4j_session_mock()

        manual_decision = make_decision_record(source="manual")
        queries_received = []

        async def mock_run(query, **params):
            queries_received.append((query, params))
            result = MagicMock()
            if "count(d) as total" in query:
                result.single = AsyncMock(return_value={"total": 1})
                return result
            elif "SKIP" in query and "LIMIT" in query:
                return create_async_result_mock([manual_decision])
            return create_async_result_mock([])

        mock_session.run = mock_run

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_graph

            await get_graph(
                page=1,
                page_size=100,
                source_filter="manual",
                user_id="test-user",
            )

            source_filter_used = any(
                "source" in str(params) and params.get("source") == "manual"
                for _, params in queries_received
            )
            assert source_filter_used

    @pytest.mark.asyncio
    async def test_filter_by_confidence(self):
        """Should filter relationships by minimum confidence."""
        mock_session = create_neo4j_session_mock()

        decision = make_decision_record()
        queries_received = []

        async def mock_run(query, **params):
            queries_received.append((query, params))
            result = MagicMock()
            if "count(d) as total" in query:
                result.single = AsyncMock(return_value={"total": 1})
                return result
            elif "DecisionTrace" in query and "SKIP" in query:
                return create_async_result_mock([decision])
            elif "INVOLVES" in query and "e:Entity" in query:
                return create_async_result_mock([])
            return create_async_result_mock([])

        mock_session.run = mock_run

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_graph

            await get_graph(
                page=1,
                page_size=100,
                min_confidence=0.8,
                user_id="test-user",
            )

            confidence_filter_used = any(
                "min_confidence" in str(params) and params.get("min_confidence") == 0.8
                for _, params in queries_received
            )
            assert confidence_filter_used

    @pytest.mark.asyncio
    async def test_filter_unknown_source(self):
        """Should handle unknown source filter for legacy decisions."""
        mock_session = create_neo4j_session_mock()

        unknown_decision = make_decision_record(source="unknown")
        queries_received = []

        async def mock_run(query, **params):
            queries_received.append((query, params))
            result = MagicMock()
            if "count(d) as total" in query:
                result.single = AsyncMock(return_value={"total": 1})
                return result
            elif "SKIP" in query:
                return create_async_result_mock([unknown_decision])
            return create_async_result_mock([])

        mock_session.run = mock_run

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_graph

            await get_graph(
                page=1,
                page_size=100,
                source_filter="unknown",
                user_id="test-user",
            )

            query_handles_null = any(
                "source IS NULL" in query for query, _ in queries_received
            )
            assert query_handles_null


# ============================================================================
# P0-3: Decision Edit Tests
# ============================================================================


class TestDecisionEdit:
    """Tests for PUT /api/decisions/{id} with edit history tracking."""

    @pytest.mark.asyncio
    async def test_update_decision_tracks_edit_history(self):
        """Should track edited_at timestamp and edit_count."""
        mock_session = create_neo4j_session_mock()
        decision_id = str(uuid4())

        original_data = {
            "d": {
                "id": decision_id,
                "trigger": "Original trigger",
                "context": "Context",
                "options": ["A", "B"],
                "decision": "A",
                "rationale": "Rationale",
                "confidence": 0.9,
                "created_at": "2024-01-01T00:00:00Z",
                "source": "manual",
            }
        }

        updated_data = {
            "d": {
                "id": decision_id,
                "trigger": "Updated trigger",
                "context": "Context",
                "options": ["A", "B"],
                "decision": "A",
                "rationale": "Rationale",
                "confidence": 0.9,
                "created_at": "2024-01-01T00:00:00Z",
                "edited_at": "2024-01-02T00:00:00Z",
                "edit_count": 1,
                "source": "manual",
            },
            "entities": [],
        }

        call_count = [0]
        update_query_captured = [None]

        async def mock_run(query, **params):
            call_count[0] += 1
            result = AsyncMock()
            if call_count[0] == 1:
                result.single = AsyncMock(return_value=original_data)
            elif call_count[0] == 2:
                update_query_captured[0] = query
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

            update_data = DecisionUpdate(trigger="Updated trigger")
            await update_decision(decision_id, update_data, user_id="test-user")

            assert update_query_captured[0] is not None
            assert "edited_at" in update_query_captured[0]
            assert "edit_count" in update_query_captured[0]

    @pytest.mark.asyncio
    async def test_update_increments_edit_count(self):
        """Should increment edit_count on each update."""
        mock_session = create_neo4j_session_mock()
        decision_id = str(uuid4())

        original_data = {
            "d": {
                "id": decision_id,
                "trigger": "Trigger",
                "context": "Context",
                "options": ["A"],
                "decision": "A",
                "rationale": "Rationale",
                "confidence": 0.9,
                "created_at": "2024-01-01T00:00:00Z",
                "edited_at": "2024-01-02T00:00:00Z",
                "edit_count": 1,
                "source": "manual",
            }
        }

        updated_data = {
            "d": {
                "id": decision_id,
                "trigger": "New trigger",
                "context": "Context",
                "options": ["A"],
                "decision": "A",
                "rationale": "Rationale",
                "confidence": 0.9,
                "created_at": "2024-01-01T00:00:00Z",
                "edited_at": "2024-01-03T00:00:00Z",
                "edit_count": 2,
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
                assert "COALESCE(d.edit_count, 0) + 1" in query
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

            update_data = DecisionUpdate(trigger="New trigger")
            result = await update_decision(
                decision_id, update_data, user_id="test-user"
            )
            assert result.trigger == "New trigger"

    @pytest.mark.asyncio
    async def test_update_requires_at_least_one_field(self):
        """Should reject update with no fields."""
        mock_session = create_neo4j_session_mock()
        decision_id = str(uuid4())

        original_data = {"d": {"id": decision_id}}

        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=original_data)
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
                    decision_id, DecisionUpdate(), user_id="test-user"
                )

            assert exc_info.value.status_code == 400
            assert "No fields to update" in exc_info.value.detail


# ============================================================================
# SD-003: Graph Pagination Tests
# ============================================================================


class TestGraphPagination:
    """Tests for GET /api/graph with pagination support."""

    @pytest.mark.asyncio
    async def test_pagination_returns_correct_metadata(self):
        """Should return correct pagination metadata."""
        mock_session = create_neo4j_session_mock()

        decisions = [make_decision_record() for _ in range(10)]

        async def mock_run(query, **params):
            result = MagicMock()
            if "count(d) as total" in query:
                result.single = AsyncMock(return_value={"total": 250})
                return result
            elif "SKIP" in query and "LIMIT" in query:
                return create_async_result_mock(decisions)
            return create_async_result_mock([])

        mock_session.run = mock_run

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_graph

            result = await get_graph(
                page=1,
                page_size=100,
                user_id="test-user",
            )

            assert result.pagination.page == 1
            assert result.pagination.page_size == 100
            assert result.pagination.total_count == 250
            assert result.pagination.total_pages == 3
            assert result.pagination.has_more is True

    @pytest.mark.asyncio
    async def test_pagination_last_page_has_no_more(self):
        """Should indicate no more pages on last page."""
        mock_session = create_neo4j_session_mock()

        async def mock_run(query, **params):
            result = MagicMock()
            if "count(d) as total" in query:
                result.single = AsyncMock(return_value={"total": 50})
                return result
            return create_async_result_mock([])

        mock_session.run = mock_run

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_graph

            result = await get_graph(
                page=1,
                page_size=100,
                user_id="test-user",
            )

            assert result.pagination.has_more is False

    @pytest.mark.asyncio
    async def test_pagination_offset_calculation(self):
        """Should calculate correct offset for page."""
        mock_session = create_neo4j_session_mock()

        params_received = []

        async def mock_run(query, **params):
            params_received.append(params)
            result = MagicMock()
            if "count(d) as total" in query:
                result.single = AsyncMock(return_value={"total": 500})
                return result
            return create_async_result_mock([])

        mock_session.run = mock_run

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_graph

            await get_graph(
                page=3,
                page_size=100,
                user_id="test-user",
            )

            offset_params = [p for p in params_received if "offset" in p]
            assert any(p.get("offset") == 200 for p in offset_params)

    @pytest.mark.asyncio
    async def test_empty_graph_pagination(self):
        """Should handle empty graph correctly."""
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

            result = await get_graph(
                page=1,
                page_size=100,
                user_id="test-user",
            )

            assert result.pagination.total_count == 0
            assert result.pagination.total_pages == 0
            assert result.pagination.has_more is False
            assert result.nodes == []
            assert result.edges == []


# ============================================================================
# SD-003: Node Neighbors Tests
# ============================================================================


class TestNodeNeighbors:
    """Tests for GET /api/graph/nodes/{id}/neighbors endpoint."""

    @pytest.mark.asyncio
    async def test_get_neighbors_returns_connected_nodes(self):
        """Should return neighbors for a valid node."""
        mock_session = create_neo4j_session_mock()
        node_id = str(uuid4())
        neighbor_id = str(uuid4())

        neighbor_data = {
            "target": {
                "id": neighbor_id,
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

        async def mock_run(query, **params):
            result = MagicMock()
            if "labels(n)" in query:
                result.single = AsyncMock(return_value={"node_type": "DecisionTrace"})
                return result
            elif "source.id = " in query:
                return create_async_result_mock([neighbor_data])
            elif "target.id = " in query:
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
                node_id=node_id,
                limit=50,
                relationship_types=None,
                user_id="test-user",
            )

            assert result.source_node_id == node_id
            assert len(result.neighbors) == 1
            assert result.neighbors[0].relationship == "INVOLVES"
            assert result.neighbors[0].direction == "outgoing"

    @pytest.mark.asyncio
    async def test_get_neighbors_includes_both_directions(self):
        """Should return both incoming and outgoing neighbors."""
        mock_session = create_neo4j_session_mock()
        node_id = str(uuid4())

        outgoing_neighbor = {
            "target": {
                "id": str(uuid4()),
                "name": "OutgoingEntity",
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

        incoming_neighbor = {
            "source": {
                "id": str(uuid4()),
                "trigger": "Incoming Decision",
                "context": "Context",
                "options": [],
                "decision": "Decision",
                "rationale": "Rationale",
                "confidence": 0.9,
                "created_at": "2024-01-01T00:00:00Z",
                "source": "manual",
            },
            "relationship": "INFLUENCED_BY",
            "weight": None,
            "score": None,
            "confidence": None,
            "source_type": "DecisionTrace",
            "has_embedding": True,
        }

        async def mock_run(query, **params):
            result = MagicMock()
            if "labels(n)" in query:
                result.single = AsyncMock(return_value={"node_type": "DecisionTrace"})
                return result
            elif "source.id = " in query:
                return create_async_result_mock([outgoing_neighbor])
            elif "target.id = " in query:
                return create_async_result_mock([incoming_neighbor])
            return create_async_result_mock([])

        mock_session.run = mock_run

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_node_neighbors

            result = await get_node_neighbors(
                node_id=node_id,
                limit=50,
                relationship_types=None,
                user_id="test-user",
            )

            assert len(result.neighbors) == 2
            directions = {n.direction for n in result.neighbors}
            assert "outgoing" in directions
            assert "incoming" in directions

    @pytest.mark.asyncio
    async def test_get_neighbors_not_found(self):
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


# ============================================================================
# P1-3: Similar Decisions Tests
# ============================================================================


class TestSimilarDecisions:
    """Tests for GET /api/graph/nodes/{id}/similar endpoint."""

    @pytest.mark.asyncio
    async def test_similar_decisions_returns_similarity_scores(self):
        """Should return similar decisions with similarity scores."""
        mock_session = create_neo4j_session_mock()
        source_id = str(uuid4())

        source_embedding = [0.1] * 2048
        similar_decision = {
            "id": str(uuid4()),
            "trigger": "Similar decision",
            "decision": "Also PostgreSQL",
            "similarity": 0.85,
            "shared_entities": ["PostgreSQL"],
        }

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.single = AsyncMock(
                    return_value={
                        "embedding": source_embedding,
                        "trigger": "Source decision",
                    }
                )
                return result
            else:
                return create_async_result_mock([similar_decision])

        mock_session.run = mock_run

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.graph import get_similar_nodes

            results = await get_similar_nodes(
                node_id=source_id,
                top_k=5,
                threshold=0.5,
                user_id="test-user",
            )

            assert len(results) >= 1
            result = results[0]
            assert hasattr(result, "similarity")
            assert result.similarity >= 0.5
            assert hasattr(result, "shared_entities")

    @pytest.mark.asyncio
    async def test_similar_decisions_not_found(self):
        """Should return 404 when decision not found."""
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

            from routers.graph import get_similar_nodes

            with pytest.raises(HTTPException) as exc_info:
                await get_similar_nodes(
                    node_id="nonexistent-id",
                    top_k=5,
                    threshold=0.5,
                    user_id="test-user",
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_similar_decisions_no_embedding(self):
        """Should return 400 when decision has no embedding."""
        mock_session = create_neo4j_session_mock()
        source_id = str(uuid4())

        mock_result = AsyncMock()
        mock_result.single = AsyncMock(
            return_value={
                "embedding": None,
                "trigger": "Decision without embedding",
            }
        )
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.graph.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from fastapi import HTTPException

            from routers.graph import get_similar_nodes

            with pytest.raises(HTTPException) as exc_info:
                await get_similar_nodes(
                    node_id=source_id,
                    top_k=5,
                    threshold=0.5,
                    user_id="test-user",
                )
            assert exc_info.value.status_code == 400
            assert "no embedding" in exc_info.value.detail.lower()
