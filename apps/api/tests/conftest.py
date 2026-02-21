"""Shared pytest fixtures for Continuum API tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from models.ontology import ResolvedEntity

# ============================================================================
# PostgreSQL Session Fixtures
# ============================================================================


@pytest.fixture
def mock_postgres_session():
    """Mock PostgreSQL async session for unit tests.

    Provides a mock SQLAlchemy async session with common operations:
    - execute: Run queries (returns mock result)
    - commit: Commit transaction
    - rollback: Rollback transaction
    - refresh: Refresh object from database
    - add: Add object to session
    - delete: Delete object from session
    - close: Close session

    Example:
        async def test_create_user(mock_postgres_session):
            mock_postgres_session.execute.return_value.scalar_one_or_none.return_value = None
            await user_service.create(mock_postgres_session, user_data)
            mock_postgres_session.commit.assert_called_once()
    """
    session = MagicMock()

    # Query execution returns a result proxy
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    result.fetchone = MagicMock(return_value=None)
    result.fetchall = MagicMock(return_value=[])
    result.rowcount = 0

    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = MagicMock()
    session.close = AsyncMock()
    session.begin = AsyncMock()

    # Context manager support
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    return session


@pytest.fixture
def mock_postgres_result_factory():
    """Factory for creating mock PostgreSQL query results.

    Example:
        def test_find_users(mock_postgres_session, mock_postgres_result_factory):
            users = [User(id=1, name="Alice"), User(id=2, name="Bob")]
            mock_postgres_session.execute.return_value = mock_postgres_result_factory(
                scalars_all=users
            )
    """

    def _create_result(
        scalar_one=None,
        scalar_one_or_none=None,
        scalars_all=None,
        fetchone=None,
        fetchall=None,
        rowcount=0,
    ):
        result = MagicMock()
        result.scalar_one = MagicMock(return_value=scalar_one)
        result.scalar_one_or_none = MagicMock(return_value=scalar_one_or_none)
        result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=scalars_all or []))
        )
        result.fetchone = MagicMock(return_value=fetchone)
        result.fetchall = MagicMock(return_value=fetchall or [])
        result.rowcount = rowcount
        return result

    return _create_result


# ============================================================================
# Neo4j Session Fixtures
# ============================================================================


@pytest.fixture
def mock_neo4j_session():
    """Create a mock Neo4j async session.

    Provides a mock Neo4j session with:
    - run: Execute Cypher queries (returns async iterable result)
    - close: Close session

    Example:
        async def test_find_node(mock_neo4j_session, mock_neo4j_result):
            mock_neo4j_session.run.return_value = mock_neo4j_result(
                records=[{"n": {"id": "123", "name": "PostgreSQL"}}]
            )
            result = await graph_service.find_node(mock_neo4j_session, "123")
    """
    session = AsyncMock()

    # Default empty result
    empty_result = AsyncMock()
    empty_result.single = AsyncMock(return_value=None)
    empty_result.__aiter__ = lambda self: self
    empty_result.__anext__ = AsyncMock(side_effect=StopAsyncIteration)

    session.run = AsyncMock(return_value=empty_result)
    session.close = AsyncMock()

    # Context manager support
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    return session


@pytest.fixture
def mock_neo4j_result():
    """Factory for creating mock Neo4j query results.

    Example:
        result = mock_neo4j_result(
            records=[
                {"n.id": "123", "n.name": "PostgreSQL"},
                {"n.id": "456", "n.name": "Redis"}
            ],
            single_value={"count": 2}
        )
    """

    def _create_result(records=None, single_value=None):
        result = AsyncMock()

        if single_value is not None:
            result.single = AsyncMock(return_value=single_value)
        else:
            result.single = AsyncMock(return_value=None)

        if records:
            # Create an async iterator
            async def async_iter():
                for record in records:
                    yield record

            result.__aiter__ = lambda: async_iter()
        else:

            async def empty_iter():
                return
                yield  # Make it a generator

            result.__aiter__ = lambda: empty_iter()

        return result

    return _create_result


# ============================================================================
# Redis Fixtures
# ============================================================================


@pytest.fixture
def mock_redis():
    """Create a mock Redis client for unit tests.

    Provides a mock Redis client with common operations:
    - get/set/delete: Basic key-value operations
    - mget/mset: Multi-key operations
    - exists: Check key existence
    - expire/ttl: TTL operations
    - incr/decr: Counter operations
    - pipeline: Transaction pipeline
    - zrangebyscore/zadd/zrem: Sorted set operations (for rate limiting)

    Example:
        async def test_cache_hit(mock_redis):
            mock_redis.get.return_value = '{"cached": "value"}'
            result = await cache_service.get("my-key")
            assert result == {"cached": "value"}
    """
    redis = AsyncMock()

    # Basic key-value operations
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.mget = AsyncMock(return_value=[])
    redis.mset = AsyncMock(return_value=True)
    redis.exists = AsyncMock(return_value=0)

    # TTL operations
    redis.expire = AsyncMock(return_value=True)
    redis.ttl = AsyncMock(return_value=-1)
    redis.setex = AsyncMock(return_value=True)

    # Counter operations
    redis.incr = AsyncMock(return_value=1)
    redis.decr = AsyncMock(return_value=0)

    # Sorted set operations (for rate limiting)
    redis.zrangebyscore = AsyncMock(return_value=[])
    redis.zadd = AsyncMock(return_value=1)
    redis.zrem = AsyncMock(return_value=1)
    redis.zremrangebyscore = AsyncMock(return_value=0)
    redis.zcard = AsyncMock(return_value=0)

    # Pipeline mock for atomic operations
    pipe = AsyncMock()
    pipe.execute = AsyncMock(return_value=[None, 5, None, None])
    pipe.zremrangebyscore = MagicMock(return_value=pipe)
    pipe.zcard = MagicMock(return_value=pipe)
    pipe.zadd = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)
    redis.pipeline = MagicMock(return_value=pipe)

    # Connection management
    redis.close = AsyncMock()
    redis.ping = AsyncMock(return_value=True)

    return redis


@pytest.fixture
def mock_redis_with_data():
    """Factory for creating a mock Redis with pre-populated data.

    Example:
        redis = mock_redis_with_data({
            "user:123": '{"name": "Alice"}',
            "session:abc": '{"user_id": "123"}'
        })
    """

    def _create_redis(data: dict):
        redis = AsyncMock()

        async def mock_get(key):
            return data.get(key)

        async def mock_set(key, value, **kwargs):
            data[key] = value
            return True

        async def mock_delete(*keys):
            count = sum(1 for k in keys if k in data)
            for k in keys:
                data.pop(k, None)
            return count

        async def mock_exists(*keys):
            return sum(1 for k in keys if k in data)

        redis.get = AsyncMock(side_effect=mock_get)
        redis.set = AsyncMock(side_effect=mock_set)
        redis.delete = AsyncMock(side_effect=mock_delete)
        redis.exists = AsyncMock(side_effect=mock_exists)
        redis.mget = AsyncMock(side_effect=lambda keys: [data.get(k) for k in keys])
        redis.close = AsyncMock()
        redis.ping = AsyncMock(return_value=True)

        return redis

    return _create_redis


# ============================================================================
# LLM Client Fixtures
# ============================================================================


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = AsyncMock()
    client.generate = AsyncMock(return_value="Mock LLM response")
    return client


@pytest.fixture
def mock_llm_json_response():
    """Factory for creating mock LLM JSON responses."""

    def _create_response(data):
        import json

        return json.dumps(data)

    return _create_response


# ============================================================================
# Embedding Service Fixtures
# ============================================================================


@pytest.fixture
def mock_embedding_service():
    """Create a mock embedding service."""
    service = AsyncMock()

    # Default: return a simple 2048-dimension embedding
    def make_embedding(text="", **kwargs):
        # Create deterministic embedding based on text hash
        seed = hash(text) % 1000000
        return [float((seed + i) % 100) / 100.0 for i in range(2048)]

    service.embed_text = AsyncMock(side_effect=make_embedding)
    service.embed_texts = AsyncMock(return_value=[[0.1] * 2048])
    service.embed_decision = AsyncMock(return_value=[0.1] * 2048)
    service.embed_entity = AsyncMock(return_value=[0.1] * 2048)
    service.dimensions = 2048

    return service


@pytest.fixture
def sample_embedding():
    """Return a sample 2048-dimension embedding vector."""
    return [0.1 * (i % 10) for i in range(2048)]


# ============================================================================
# Entity Fixtures
# ============================================================================


@pytest.fixture
def sample_entity():
    """Return a single sample entity for testing.

    Includes all standard fields expected by the API.
    """
    return {
        "id": "test-entity-123",
        "name": "PostgreSQL",
        "type": "technology",
        "description": "Open-source relational database management system",
        "created_at": "2026-01-29T12:00:00Z",
        "updated_at": "2026-01-29T12:00:00Z",
    }


@pytest.fixture
def sample_entities():
    """Return a list of sample entities for testing."""
    return [
        {
            "id": str(uuid4()),
            "name": "PostgreSQL",
            "type": "technology",
            "description": "Open-source relational database",
        },
        {
            "id": str(uuid4()),
            "name": "Redis",
            "type": "technology",
            "description": "In-memory data structure store",
        },
        {
            "id": str(uuid4()),
            "name": "Microservices",
            "type": "concept",
            "description": "Architectural style using small, independent services",
        },
        {
            "id": str(uuid4()),
            "name": "REST API",
            "type": "pattern",
            "description": "Representational State Transfer API design pattern",
        },
        {
            "id": str(uuid4()),
            "name": "Alice Johnson",
            "type": "person",
            "description": "Senior Software Engineer",
        },
        {
            "id": str(uuid4()),
            "name": "acme-project",
            "type": "project",
            "description": "Main project repository",
        },
    ]


@pytest.fixture
def sample_resolved_entity():
    """Return a sample ResolvedEntity."""
    return ResolvedEntity(
        id=str(uuid4()),
        name="PostgreSQL",
        type="technology",
        is_new=False,
        match_method="exact",
        confidence=1.0,
    )


@pytest.fixture
def sample_entity_types():
    """Return all valid entity types for testing."""
    return ["technology", "concept", "pattern", "person", "project", "other"]


# ============================================================================
# Decision Fixtures
# ============================================================================


@pytest.fixture
def sample_decision():
    """Return a single sample decision with all standard fields.

    Includes the full decision trace structure as documented in CLAUDE.md.
    """
    return {
        "id": "test-decision-123",
        "title": "Use PostgreSQL for data storage",
        "trigger": "Need to choose a database for persistent storage",
        "context": "Building a new web application that requires complex queries, "
        "joins, and ACID compliance. Expected data volume is moderate.",
        "options": ["PostgreSQL", "MySQL", "MongoDB", "SQLite"],
        "decision": "PostgreSQL",
        "rationale": "PostgreSQL offers the best combination of features for our needs: "
        "robust JSON support, excellent query performance, strong consistency, "
        "and a mature ecosystem with good tooling.",
        "source": "test-session-abc",
        "timestamp": "2026-01-29T12:00:00Z",
        "user_id": "test-user-456",
        "created_at": "2026-01-29T12:00:00Z",
        "updated_at": "2026-01-29T12:00:00Z",
    }


@pytest.fixture
def sample_decisions():
    """Return a list of sample decisions for testing."""
    return [
        {
            "id": str(uuid4()),
            "title": "Database Selection",
            "trigger": "Need to choose a database",
            "context": "Building a new application with complex queries",
            "options": ["PostgreSQL", "MongoDB", "MySQL"],
            "decision": "Use PostgreSQL",
            "rationale": "Better for relational data and complex queries",
            "source": "planning-session-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "user_id": "user-001",
            "created_at": "2026-01-01T00:00:00Z",
            "entities": ["PostgreSQL", "MongoDB"],
        },
        {
            "id": str(uuid4()),
            "title": "Caching Strategy",
            "trigger": "Need to implement caching",
            "context": "Application performance is slow under load",
            "options": ["Redis", "Memcached", "In-memory"],
            "decision": "Use Redis",
            "rationale": "Redis provides better data structures and persistence options",
            "source": "performance-review-1",
            "timestamp": "2026-01-02T00:00:00Z",
            "user_id": "user-001",
            "created_at": "2026-01-02T00:00:00Z",
            "entities": ["Redis", "Memcached"],
        },
        {
            "id": str(uuid4()),
            "title": "API Framework Choice",
            "trigger": "Need to build REST API",
            "context": "Require async support and automatic documentation",
            "options": ["FastAPI", "Django REST", "Flask"],
            "decision": "FastAPI",
            "rationale": "Best async support and auto-generated OpenAPI docs",
            "source": "architecture-meeting-1",
            "timestamp": "2026-01-03T00:00:00Z",
            "user_id": "user-002",
            "created_at": "2026-01-03T00:00:00Z",
            "entities": ["FastAPI", "Django", "Flask"],
        },
    ]


@pytest.fixture
def sample_decision_minimal():
    """Return a minimal valid decision (only required fields)."""
    return {
        "trigger": "Choosing an approach",
        "decision": "Selected option A",
        "rationale": "It was the best fit",
    }


# ============================================================================
# Relationship Fixtures
# ============================================================================


@pytest.fixture
def sample_relationships():
    """Return sample relationship data for testing graph operations."""
    return [
        {
            "type": "INVOLVES",
            "from_id": "decision-123",
            "to_id": "entity-456",
            "properties": {"role": "primary"},
        },
        {
            "type": "DEPENDS_ON",
            "from_id": "entity-456",
            "to_id": "entity-789",
            "properties": {"reason": "runtime dependency"},
        },
        {
            "type": "SUPERSEDES",
            "from_id": "decision-999",
            "to_id": "decision-123",
            "properties": {"reason": "updated requirements"},
        },
    ]


@pytest.fixture
def sample_relationship_types():
    """Return all valid relationship types for testing."""
    return {
        "entity_entity": [
            "IS_A",
            "PART_OF",
            "DEPENDS_ON",
            "RELATED_TO",
            "ALTERNATIVE_TO",
        ],
        "decision_entity": ["INVOLVES"],
        "decision_decision": [
            "SIMILAR_TO",
            "INFLUENCED_BY",
            "SUPERSEDES",
            "CONTRADICTS",
        ],
    }


# ============================================================================
# HTTP Client Fixtures
# ============================================================================


@pytest.fixture
def mock_openai_response():
    """Create a mock OpenAI API response."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "Mock response"
    return response


@pytest.fixture
def mock_embedding_response():
    """Create a mock embedding API response."""
    response = MagicMock()
    response.data = [MagicMock()]
    response.data[0].embedding = [0.1] * 2048
    return response


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx async client for external API testing."""
    client = AsyncMock()

    response = MagicMock()
    response.status_code = 200
    response.json = MagicMock(return_value={})
    response.text = ""
    response.raise_for_status = MagicMock()

    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    client.put = AsyncMock(return_value=response)
    client.delete = AsyncMock(return_value=response)
    client.close = AsyncMock()

    # Context manager support
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    return client


# ============================================================================
# Validation Issue Fixtures
# ============================================================================


@pytest.fixture
def sample_validation_issues():
    """Return sample validation issues."""
    from services.validator import IssueSeverity, IssueType, ValidationIssue

    return [
        ValidationIssue(
            type=IssueType.CIRCULAR_DEPENDENCY,
            severity=IssueSeverity.ERROR,
            message="Circular dependency: A -> B -> A",
            affected_nodes=["id1", "id2"],
            suggested_action="Remove the cycle",
            details={"cycle": ["A", "B", "A"]},
        ),
        ValidationIssue(
            type=IssueType.ORPHAN_ENTITY,
            severity=IssueSeverity.WARNING,
            message="Orphan entity: Unused Technology",
            affected_nodes=["id3"],
            suggested_action="Link or delete",
        ),
    ]


# ============================================================================
# Authentication Fixtures
# ============================================================================


@pytest.fixture
def sample_user():
    """Return a sample user for authentication testing."""
    return {
        "id": "test-user-456",
        "email": "testuser@example.com",
        "name": "Test User",
        "image": "https://example.com/avatar.png",
        "created_at": "2026-01-01T00:00:00Z",
    }


@pytest.fixture
def sample_jwt_token():
    """Return a sample JWT token payload."""
    return {
        "sub": "test-user-456",
        "email": "testuser@example.com",
        "name": "Test User",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,  # 1 hour
    }


@pytest.fixture
def mock_auth_dependency():
    """Mock the authentication dependency for protected route testing."""

    async def _get_current_user():
        return {"id": "test-user-456", "email": "testuser@example.com"}

    return _get_current_user
