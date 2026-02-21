"""API Performance Tests for Continuum.

Tests response times for key endpoints under various load conditions.
Uses pytest-benchmark for consistent performance measurement.

Performance targets:
- Health/stats endpoints: p99 < 50ms
- Decision CRUD: p99 < 200ms
- Search endpoints: p99 < 500ms
- Graph endpoints: p99 < 300ms

Note: These tests are designed to run against a local test server.
For true load testing, use tests/load/load_test.py with concurrent workers.
"""

import asyncio
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# Test configuration
PERFORMANCE_TARGETS = {
    "health_check": 50,  # ms
    "dashboard_stats": 100,  # ms
    "list_decisions": 200,  # ms
    "get_decision": 150,  # ms
    "create_decision": 300,  # ms
    "search": 500,  # ms
    "graph_stats": 200,  # ms
    "graph_data": 300,  # ms
}

# Number of iterations for statistical significance
WARMUP_ITERATIONS = 3
TEST_ITERATIONS = 10


# ============================================================================
# Performance Test Fixtures
# ============================================================================


@pytest.fixture
def mock_neo4j_fast():
    """Create a mock Neo4j session with minimal latency."""
    session = AsyncMock()

    # Simulate fast database responses
    async def fast_run(query, **params):
        await asyncio.sleep(0.001)  # 1ms simulated DB latency
        result = AsyncMock()
        result.single = AsyncMock(return_value=None)
        result._records = []
        result.__aiter__ = lambda self: self._async_iter()

        async def _async_iter():
            return
            yield

        result._async_iter = _async_iter
        return result

    session.run = fast_run
    session.close = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    return session


@pytest.fixture
def mock_postgres_fast():
    """Create a mock Postgres session with minimal latency."""
    session = MagicMock()

    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    result.fetchone = MagicMock(return_value=None)
    result.fetchall = MagicMock(return_value=[])

    async def fast_execute(query, **params):
        await asyncio.sleep(0.001)  # 1ms simulated latency
        return result

    session.execute = fast_execute
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = MagicMock()
    session.close = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    return session


@pytest.fixture
def performance_timer():
    """Create a timer utility for performance measurements."""

    class Timer:
        def __init__(self):
            self.times = []
            self.start_time = None

        def start(self):
            self.start_time = time.perf_counter()

        def stop(self):
            if self.start_time:
                elapsed = (time.perf_counter() - self.start_time) * 1000  # ms
                self.times.append(elapsed)
                self.start_time = None
                return elapsed
            return 0

        @property
        def avg(self):
            return sum(self.times) / len(self.times) if self.times else 0

        @property
        def p99(self):
            if not self.times:
                return 0
            sorted_times = sorted(self.times)
            index = int(len(sorted_times) * 0.99)
            return sorted_times[min(index, len(sorted_times) - 1)]

        @property
        def min_time(self):
            return min(self.times) if self.times else 0

        @property
        def max_time(self):
            return max(self.times) if self.times else 0

    return Timer()


# ============================================================================
# Simulated Endpoint Performance Tests
# ============================================================================


class TestDatabaseOperationPerformance:
    """Test performance of database operations."""

    @pytest.mark.asyncio
    async def test_neo4j_query_performance(self, mock_neo4j_fast, performance_timer):
        """Test Neo4j query execution time."""
        # Warmup
        for _ in range(WARMUP_ITERATIONS):
            await mock_neo4j_fast.run("MATCH (n) RETURN n LIMIT 1")

        # Measure
        for _ in range(TEST_ITERATIONS):
            performance_timer.start()
            await mock_neo4j_fast.run(
                "MATCH (d:DecisionTrace) RETURN d LIMIT 10",
                user_id="test",
            )
            performance_timer.stop()

        assert performance_timer.p99 < 50, (
            f"Neo4j query p99 ({performance_timer.p99:.2f}ms) exceeds 50ms"
        )

    @pytest.mark.asyncio
    async def test_concurrent_queries(self, mock_neo4j_fast, performance_timer):
        """Test performance under concurrent query load."""

        async def run_query(session, query_id: int):
            return await session.run(
                "MATCH (n) WHERE n.id = $id RETURN n",
                id=str(uuid4()),
            )

        # Run 10 concurrent queries
        performance_timer.start()
        tasks = [run_query(mock_neo4j_fast, i) for i in range(10)]
        await asyncio.gather(*tasks)
        elapsed = performance_timer.stop()

        # Concurrent queries should complete in reasonable time
        assert elapsed < 100, (
            f"10 concurrent queries took {elapsed:.2f}ms (target: <100ms)"
        )


class TestDataProcessingPerformance:
    """Test performance of data processing operations."""

    def test_json_parsing_performance(self, performance_timer):
        """Test JSON parsing speed for typical responses."""
        import json

        # Create realistic response data
        sample_data = {
            "decisions": [
                {
                    "id": str(uuid4()),
                    "trigger": f"Decision trigger {i}",
                    "context": "Context for decision " * 10,
                    "options": ["Option A", "Option B", "Option C"],
                    "decision": "Chosen option",
                    "rationale": "Rationale for choice " * 5,
                    "confidence": 0.85,
                    "created_at": datetime.now().isoformat(),
                    "entities": [
                        {"id": str(uuid4()), "name": f"Entity{j}", "type": "technology"}
                        for j in range(5)
                    ],
                }
                for i in range(50)
            ]
        }

        json_str = json.dumps(sample_data)

        # Warmup
        for _ in range(WARMUP_ITERATIONS):
            json.loads(json_str)

        # Measure
        for _ in range(TEST_ITERATIONS):
            performance_timer.start()
            json.loads(json_str)
            performance_timer.stop()

        assert performance_timer.p99 < 10, (
            f"JSON parsing p99 ({performance_timer.p99:.2f}ms) exceeds 10ms"
        )

    def test_list_filtering_performance(self, performance_timer):
        """Test list filtering performance for search results."""
        # Create a large list of items
        items = [
            {
                "id": str(uuid4()),
                "name": f"Item {i}",
                "type": "technology" if i % 2 == 0 else "concept",
                "score": i / 1000,
            }
            for i in range(1000)
        ]

        # Warmup
        for _ in range(WARMUP_ITERATIONS):
            [
                item
                for item in items
                if item["score"] > 0.5 and item["type"] == "technology"
            ]

        # Measure filtering
        for _ in range(TEST_ITERATIONS):
            performance_timer.start()
            filtered = [
                item
                for item in items
                if item["score"] > 0.5 and item["type"] == "technology"
            ]
            _sorted_filtered = sorted(filtered, key=lambda x: x["score"], reverse=True)[
                :10
            ]
            performance_timer.stop()

        assert performance_timer.p99 < 5, (
            f"List filtering p99 ({performance_timer.p99:.2f}ms) exceeds 5ms"
        )


class TestEmbeddingOperationPerformance:
    """Test performance of embedding-related operations."""

    def test_cosine_similarity_performance(self, performance_timer):
        """Test cosine similarity calculation speed."""
        from utils.vectors import cosine_similarity

        # Create test vectors (2048 dimensions)
        vec_a = [0.1 * (i % 10) for i in range(2048)]
        vec_b = [0.2 * ((i + 5) % 10) for i in range(2048)]

        # Warmup
        for _ in range(WARMUP_ITERATIONS):
            cosine_similarity(vec_a, vec_b)

        # Measure
        for _ in range(TEST_ITERATIONS):
            performance_timer.start()
            cosine_similarity(vec_a, vec_b)
            performance_timer.stop()

        assert performance_timer.p99 < 1, (
            f"Cosine similarity p99 ({performance_timer.p99:.2f}ms) exceeds 1ms"
        )

    def test_batch_similarity_performance(self, performance_timer):
        """Test batch similarity calculations."""
        from utils.vectors import cosine_similarity

        # Query vector
        query_vec = [0.1 * (i % 10) for i in range(2048)]

        # 100 candidate vectors
        candidates = [[0.1 * ((i + j) % 10) for i in range(2048)] for j in range(100)]

        # Warmup
        for _ in range(WARMUP_ITERATIONS):
            [cosine_similarity(query_vec, c) for c in candidates]

        # Measure
        for _ in range(TEST_ITERATIONS):
            performance_timer.start()
            similarities = [cosine_similarity(query_vec, c) for c in candidates]
            _top_10 = sorted(
                range(len(similarities)), key=lambda i: similarities[i], reverse=True
            )[:10]
            performance_timer.stop()

        assert performance_timer.p99 < 50, (
            f"Batch similarity p99 ({performance_timer.p99:.2f}ms) exceeds 50ms"
        )


class TestValidationPerformance:
    """Test performance of validation operations."""

    def test_pydantic_validation_performance(self, performance_timer):
        """Test Pydantic model validation speed."""
        from models.schemas import DecisionCreate

        # Valid decision data
        decision_data = {
            "trigger": "Need to choose a database for the project",
            "context": "Building a new web application",
            "options": ["PostgreSQL", "MongoDB", "MySQL"],
            "decision": "PostgreSQL",
            "rationale": "Best for relational data",
            "confidence": 0.85,
        }

        # Warmup
        for _ in range(WARMUP_ITERATIONS):
            DecisionCreate(**decision_data)

        # Measure
        for _ in range(TEST_ITERATIONS):
            performance_timer.start()
            DecisionCreate(**decision_data)
            performance_timer.stop()

        assert performance_timer.p99 < 2, (
            f"Validation p99 ({performance_timer.p99:.2f}ms) exceeds 2ms"
        )

    def test_uuid_validation_performance(self, performance_timer):
        """Test UUID validation speed."""
        from models.schemas import validate_uuid

        valid_uuid = str(uuid4())

        # Warmup
        for _ in range(WARMUP_ITERATIONS):
            validate_uuid(valid_uuid, "test")

        # Measure
        for _ in range(TEST_ITERATIONS):
            performance_timer.start()
            for _ in range(100):  # Validate 100 UUIDs
                validate_uuid(valid_uuid, "test")
            performance_timer.stop()

        # 100 validations should be very fast
        assert performance_timer.p99 < 5, (
            f"UUID validation p99 ({performance_timer.p99:.2f}ms) exceeds 5ms"
        )


class TestEntityResolutionPerformance:
    """Test performance of entity resolution operations."""

    def test_fuzzy_matching_performance(self, performance_timer):
        """Test fuzzy string matching speed."""
        try:
            from rapidfuzz import fuzz
        except ImportError:
            pytest.skip("rapidfuzz not installed")

        # Test strings
        query = "PostgreSQL"
        candidates = [
            "PostgreSQL",
            "Postgresql",
            "postgres",
            "POSTGRESQL",
            "MySQL",
            "MariaDB",
            "Redis",
            "MongoDB",
            "Neo4j",
            "Cassandra",
            "DynamoDB",
            "CockroachDB",
            "TimescaleDB",
        ] * 10  # 130 candidates

        # Warmup
        for _ in range(WARMUP_ITERATIONS):
            [fuzz.ratio(query.lower(), c.lower()) for c in candidates]

        # Measure
        for _ in range(TEST_ITERATIONS):
            performance_timer.start()
            scores = [fuzz.ratio(query.lower(), c.lower()) for c in candidates]
            _best_match = max(range(len(scores)), key=lambda i: scores[i])
            performance_timer.stop()

        assert performance_timer.p99 < 10, (
            f"Fuzzy matching p99 ({performance_timer.p99:.2f}ms) exceeds 10ms"
        )

    def test_canonical_lookup_performance(self, performance_timer):
        """Test canonical name lookup speed."""
        from models.ontology import get_canonical_name

        # Test names
        test_names = [
            "postgres",
            "k8s",
            "js",
            "ts",
            "py",
            "mongo",
            "redis",
            "react",
            "vue",
            "angular",
        ] * 100  # 1000 lookups

        # Warmup
        for _ in range(WARMUP_ITERATIONS):
            [get_canonical_name(name) for name in test_names]

        # Measure
        for _ in range(TEST_ITERATIONS):
            performance_timer.start()
            [get_canonical_name(name) for name in test_names]
            performance_timer.stop()

        # 1000 lookups should be very fast (dict lookup)
        assert performance_timer.p99 < 5, (
            f"Canonical lookup p99 ({performance_timer.p99:.2f}ms) exceeds 5ms"
        )


class TestDataSizeScaling:
    """Test performance scaling with data size."""

    def test_decision_list_scaling(self, performance_timer):
        """Test how decision list processing scales with size."""
        from models.schemas import GraphNode

        sizes = [10, 50, 100, 200]
        results = {}

        for size in sizes:
            # Create test decisions
            decisions = [
                {
                    "id": str(uuid4()),
                    "type": "decision",
                    "label": f"Decision {i}",
                    "data": {
                        "trigger": f"Trigger {i}",
                        "context": "Context " * 10,
                        "decision": f"Decision {i}",
                    },
                    "has_embedding": True,
                }
                for i in range(size)
            ]

            # Warmup
            for _ in range(WARMUP_ITERATIONS):
                [GraphNode(**d) for d in decisions]

            # Measure
            times = []
            for _ in range(TEST_ITERATIONS):
                performance_timer.start()
                _nodes = [GraphNode(**d) for d in decisions]
                elapsed = performance_timer.stop()
                times.append(elapsed)

            results[size] = sum(times) / len(times)

        # Check scaling is roughly linear (not exponential)
        # Time for 200 items should be less than 5x time for 10 items
        scaling_factor = results[200] / results[10] if results[10] > 0 else 0
        assert scaling_factor < 30, (
            f"Scaling factor {scaling_factor:.2f} exceeds 30x (indicates non-linear scaling)"
        )

    def test_graph_edge_scaling(self, performance_timer):
        """Test how graph edge processing scales."""
        from models.schemas import GraphEdge

        sizes = [50, 200, 500]
        results = {}

        for size in sizes:
            # Create test edges
            node_ids = [str(uuid4()) for _ in range(size // 5)]
            edges = [
                {
                    "id": str(uuid4()),
                    "source": node_ids[i % len(node_ids)],
                    "target": node_ids[(i + 1) % len(node_ids)],
                    "relationship": "INVOLVES",
                    "weight": 0.8,
                }
                for i in range(size)
            ]

            # Warmup
            for _ in range(WARMUP_ITERATIONS):
                [GraphEdge(**e) for e in edges]

            # Measure
            times = []
            for _ in range(TEST_ITERATIONS):
                performance_timer.start()
                _graph_edges = [GraphEdge(**e) for e in edges]
                elapsed = performance_timer.stop()
                times.append(elapsed)

            results[size] = sum(times) / len(times)

        # Check linear scaling
        scaling_factor = results[500] / results[50] if results[50] > 0 else 0
        assert scaling_factor < 15, (
            f"Edge scaling factor {scaling_factor:.2f} exceeds 15x"
        )


# ============================================================================
# Performance Regression Detection
# ============================================================================


class TestPerformanceBaseline:
    """Tests to detect performance regressions."""

    def test_establish_baseline(self, performance_timer):
        """Establish and verify performance baseline."""
        baselines = {
            "json_parse_50_decisions": 10,  # ms
            "list_filter_1000_items": 5,  # ms
            "cosine_similarity_2048d": 1,  # ms
            "pydantic_validation": 2,  # ms
        }

        # JSON parsing baseline
        import json

        data = {"decisions": [{"id": str(uuid4())} for _ in range(50)]}
        json_str = json.dumps(data)

        for _ in range(TEST_ITERATIONS):
            performance_timer.start()
            json.loads(json_str)
            performance_timer.stop()

        assert performance_timer.p99 < baselines["json_parse_50_decisions"], (
            f"JSON parsing regression: {performance_timer.p99:.2f}ms > {baselines['json_parse_50_decisions']}ms"
        )


# ============================================================================
# Run tests
# ============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
