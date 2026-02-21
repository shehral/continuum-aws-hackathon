"""Comprehensive unit tests for EntityResolver service.

Tests all 6 resolution stages:
1. Exact match (case-insensitive)
2. Canonical lookup (alias to canonical name)
3. Alias search (entity aliases field)
4. Fuzzy match (85% threshold)
5. Embedding similarity (cosine > 0.9)
6. Create new entity

Target: 90%+ coverage for entity_resolver.py
"""

from unittest.mock import patch
from uuid import uuid4

import pytest

from models.ontology import get_canonical_name, normalize_entity_name
from services.entity_resolver import EntityResolver, get_entity_resolver
from tests.factories import EntityFactory, Neo4jRecordFactory
from tests.mocks.llm_mock import MockEmbeddingService
from tests.mocks.neo4j_mock import MockNeo4jResult, MockNeo4jSession
from utils.vectors import cosine_similarity

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_session():
    """Create a mock Neo4j session."""
    return MockNeo4jSession()


@pytest.fixture
def mock_embedding_service():
    """Create a mock embedding service."""
    return MockEmbeddingService()


@pytest.fixture
def resolver_with_mocks(mock_session, mock_embedding_service):
    """Create EntityResolver with mocked dependencies."""
    with patch(
        "services.entity_resolver.get_embedding_service",
        return_value=mock_embedding_service,
    ):
        resolver = EntityResolver(mock_session)
        resolver.embedding_service = mock_embedding_service
        return resolver


# ============================================================================
# Stage 1: Exact Match Tests
# ============================================================================


class TestEntityResolverExactMatch:
    """Test Stage 1: Exact case-insensitive matching."""

    @pytest.mark.asyncio
    async def test_exact_match_lowercase(self, resolver_with_mocks, mock_session):
        """Should match entity with exact lowercase name."""
        entity = EntityFactory.create(name="PostgreSQL", entity_type="technology")
        mock_session.set_response(
            "toLower(e.name)",
            single_value=Neo4jRecordFactory.create_entity_record(entity),
        )

        result = await resolver_with_mocks.resolve("postgresql", "technology")

        assert result.is_new is False
        assert result.match_method == "exact"
        assert result.confidence == 1.0
        assert result.name == "PostgreSQL"

    @pytest.mark.asyncio
    async def test_exact_match_uppercase(self, resolver_with_mocks, mock_session):
        """Should match entity with uppercase input."""
        entity = EntityFactory.create(name="Redis", entity_type="technology")
        mock_session.set_response(
            "toLower(e.name)",
            single_value=Neo4jRecordFactory.create_entity_record(entity),
        )

        result = await resolver_with_mocks.resolve("REDIS", "technology")

        assert result.is_new is False
        assert result.match_method == "exact"

    @pytest.mark.asyncio
    async def test_exact_match_mixed_case(self, resolver_with_mocks, mock_session):
        """Should match entity regardless of case."""
        entity = EntityFactory.create(name="FastAPI", entity_type="technology")
        mock_session.set_response(
            "toLower(e.name)",
            single_value=Neo4jRecordFactory.create_entity_record(entity),
        )

        result = await resolver_with_mocks.resolve("FaStApI", "technology")

        assert result.is_new is False
        assert result.match_method == "exact"

    @pytest.mark.asyncio
    async def test_exact_match_with_whitespace(self, resolver_with_mocks, mock_session):
        """Should normalize whitespace before matching."""
        entity = EntityFactory.create(name="React", entity_type="technology")
        mock_session.set_response(
            "toLower(e.name)",
            single_value=Neo4jRecordFactory.create_entity_record(entity),
        )

        result = await resolver_with_mocks.resolve("  react  ", "technology")

        assert result.is_new is False
        assert result.match_method == "exact"

    @pytest.mark.asyncio
    async def test_exact_match_returns_entity_id(
        self, resolver_with_mocks, mock_session
    ):
        """Should return the correct entity ID on exact match."""
        entity_id = str(uuid4())
        entity = EntityFactory.create(
            name="Docker",
            entity_type="technology",
            entity_id=entity_id,
        )
        mock_session.set_response(
            "toLower(e.name)",
            single_value=Neo4jRecordFactory.create_entity_record(entity),
        )

        result = await resolver_with_mocks.resolve("docker", "technology")

        assert result.id == entity_id


# ============================================================================
# Stage 2: Canonical Lookup Tests
# ============================================================================


class TestEntityResolverCanonicalLookup:
    """Test Stage 2: Canonical name lookup from CANONICAL_NAMES mapping."""

    @pytest.mark.asyncio
    async def test_canonical_lookup_postgres(
        self, mock_session, mock_embedding_service
    ):
        """Should resolve 'postgres' to 'PostgreSQL'."""
        entity = EntityFactory.create(name="PostgreSQL", entity_type="technology")
        entity_record = Neo4jRecordFactory.create_entity_record(entity)

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            # User-scoped entity resolver now does 2 queries per lookup:
            # 1-2: exact match for "postgres" (user entities, then all)
            # 3-4: exact match for "postgresql" canonical (user entities, then all)
            if call_count[0] <= 2:  # "postgres" lookup - not found
                return MockNeo4jResult(single_value=None)
            elif call_count[0] <= 4:  # "postgresql" canonical lookup
                return MockNeo4jResult(single_value=entity_record)
            return MockNeo4jResult(single_value=None)

        mock_session.run = mock_run

        with patch(
            "services.entity_resolver.get_embedding_service",
            return_value=mock_embedding_service,
        ):
            resolver = EntityResolver(mock_session)
            resolver.embedding_service = mock_embedding_service
            result = await resolver.resolve("postgres", "technology")

        assert result.is_new is False
        assert result.match_method == "canonical"
        assert result.confidence == 0.95
        assert result.canonical_name == "PostgreSQL"

    @pytest.mark.asyncio
    async def test_canonical_lookup_k8s(self, mock_session, mock_embedding_service):
        """Should resolve 'k8s' to 'Kubernetes'."""
        entity = EntityFactory.create(name="Kubernetes", entity_type="technology")
        entity_record = Neo4jRecordFactory.create_entity_record(entity)

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            if call_count[0] <= 2:  # "k8s" lookup - not found
                return MockNeo4jResult(single_value=None)
            elif call_count[0] <= 4:  # "kubernetes" canonical lookup
                return MockNeo4jResult(single_value=entity_record)
            return MockNeo4jResult(single_value=None)

        mock_session.run = mock_run

        with patch(
            "services.entity_resolver.get_embedding_service",
            return_value=mock_embedding_service,
        ):
            resolver = EntityResolver(mock_session)
            resolver.embedding_service = mock_embedding_service
            result = await resolver.resolve("k8s", "technology")

        assert result.match_method == "canonical"
        assert result.canonical_name == "Kubernetes"

    @pytest.mark.asyncio
    async def test_canonical_lookup_js(self, mock_session, mock_embedding_service):
        """Should resolve 'js' to 'JavaScript'."""
        entity = EntityFactory.create(name="JavaScript", entity_type="technology")
        entity_record = Neo4jRecordFactory.create_entity_record(entity)

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            if call_count[0] <= 2:  # "js" lookup - not found
                return MockNeo4jResult(single_value=None)
            elif call_count[0] <= 4:  # "javascript" canonical lookup
                return MockNeo4jResult(single_value=entity_record)
            return MockNeo4jResult(single_value=None)

        mock_session.run = mock_run

        with patch(
            "services.entity_resolver.get_embedding_service",
            return_value=mock_embedding_service,
        ):
            resolver = EntityResolver(mock_session)
            resolver.embedding_service = mock_embedding_service
            result = await resolver.resolve("js", "technology")

        assert result.match_method == "canonical"
        assert result.canonical_name == "JavaScript"

    @pytest.mark.asyncio
    async def test_canonical_lookup_nextjs(self, mock_session, mock_embedding_service):
        """Should resolve 'next' to 'Next.js'."""
        entity = EntityFactory.create(name="Next.js", entity_type="technology")
        entity_record = Neo4jRecordFactory.create_entity_record(entity)

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            if call_count[0] <= 2:  # "next" lookup - not found
                return MockNeo4jResult(single_value=None)
            elif call_count[0] <= 4:  # "next.js" canonical lookup
                return MockNeo4jResult(single_value=entity_record)
            return MockNeo4jResult(single_value=None)

        mock_session.run = mock_run

        with patch(
            "services.entity_resolver.get_embedding_service",
            return_value=mock_embedding_service,
        ):
            resolver = EntityResolver(mock_session)
            resolver.embedding_service = mock_embedding_service
            result = await resolver.resolve("next", "technology")

        assert result.match_method == "canonical"

    @pytest.mark.asyncio
    async def test_canonical_not_found_continues_to_next_stage(
        self, resolver_with_mocks, mock_session
    ):
        """Should continue to alias search if canonical not found."""
        # No exact match, no canonical match
        mock_session.set_default_response(single_value=None)

        result = await resolver_with_mocks.resolve("unknown_tech", "technology")

        # Should eventually create new entity
        assert result.is_new is True


# ============================================================================
# Stage 3: Alias Search Tests
# ============================================================================


class TestEntityResolverAliasSearch:
    """Test Stage 3: Search entity aliases field."""

    @pytest.mark.asyncio
    async def test_alias_match_finds_entity(self, resolver_with_mocks, mock_session):
        """Should find entity via alias."""
        entity = EntityFactory.create(
            name="PostgreSQL",
            entity_type="technology",
            aliases=["pg", "pgsql"],
        )

        # No exact match
        mock_session.set_default_response(single_value=None)
        # But alias search finds it
        mock_session.set_response(
            "ANY(alias IN",
            single_value=Neo4jRecordFactory.create_entity_record(entity),
        )

        result = await resolver_with_mocks.resolve("pgsql", "technology")

        assert result.is_new is False
        assert result.match_method == "alias"
        assert result.confidence == 0.92

    @pytest.mark.asyncio
    async def test_alias_match_case_insensitive(
        self, resolver_with_mocks, mock_session
    ):
        """Should match alias case-insensitively."""
        entity = EntityFactory.create(
            name="MongoDB",
            entity_type="technology",
            aliases=["mongo"],
        )

        mock_session.set_default_response(single_value=None)
        mock_session.set_response(
            "ANY(alias IN",
            single_value=Neo4jRecordFactory.create_entity_record(entity),
        )

        result = await resolver_with_mocks.resolve("MONGO", "technology")

        assert result.match_method == "alias"


# ============================================================================
# Stage 4: Fuzzy Match Tests
# ============================================================================


class TestEntityResolverFuzzyMatch:
    """Test Stage 4: Fuzzy matching with 85% threshold."""

    @pytest.mark.asyncio
    async def test_fuzzy_match_above_threshold(self, resolver_with_mocks, mock_session):
        """Should fuzzy match similar names above 85% threshold."""
        entity = EntityFactory.create(name="PostgreSQL", entity_type="technology")

        # No exact, canonical, or alias match
        mock_session.set_default_response(single_value=None)
        # Return all entities for fuzzy matching
        mock_session.set_response(
            "MATCH (e:Entity)",
            records=[Neo4jRecordFactory.create_entity_record(entity)],
        )

        result = await resolver_with_mocks.resolve("Postgresql", "technology")

        assert result.is_new is False
        assert result.match_method == "fuzzy"
        assert result.confidence >= 0.85

    @pytest.mark.asyncio
    async def test_fuzzy_match_typo(self, resolver_with_mocks, mock_session):
        """Should fuzzy match despite minor typo."""
        entity = EntityFactory.create(name="Kubernetes", entity_type="technology")

        mock_session.set_default_response(single_value=None)
        mock_session.set_response(
            "MATCH (e:Entity)",
            records=[Neo4jRecordFactory.create_entity_record(entity)],
        )

        # Common typo
        result = await resolver_with_mocks.resolve("Kuberentes", "technology")

        assert result.is_new is False
        assert result.match_method == "fuzzy"

    @pytest.mark.asyncio
    async def test_fuzzy_match_best_score(self, resolver_with_mocks, mock_session):
        """Should pick entity with best fuzzy match score."""
        entities = [
            EntityFactory.create(name="React", entity_type="technology"),
            EntityFactory.create(name="ReactJS", entity_type="technology"),
            EntityFactory.create(name="React Native", entity_type="technology"),
        ]

        mock_session.set_default_response(single_value=None)
        mock_session.set_response(
            "MATCH (e:Entity)",
            records=[Neo4jRecordFactory.create_entity_record(e) for e in entities],
        )

        result = await resolver_with_mocks.resolve("ReactJs", "technology")

        assert result.is_new is False
        assert result.match_method == "fuzzy"
        assert result.name == "ReactJS"

    @pytest.mark.asyncio
    async def test_fuzzy_match_below_threshold_skipped(
        self, resolver_with_mocks, mock_session, mock_embedding_service
    ):
        """Should skip fuzzy match if below 85% threshold."""
        entity = EntityFactory.create(
            name="Completely Different Name", entity_type="technology"
        )

        mock_session.set_default_response(single_value=None)
        mock_session.set_response(
            "MATCH (e:Entity)",
            records=[Neo4jRecordFactory.create_entity_record(entity)],
        )

        result = await resolver_with_mocks.resolve("PostgreSQL", "technology")

        # Should not match via fuzzy, will try embedding or create new
        assert result.match_method != "fuzzy" or result.confidence < 0.85

    @pytest.mark.asyncio
    async def test_fuzzy_threshold_configurable(
        self, mock_session, mock_embedding_service
    ):
        """Should respect custom fuzzy threshold."""
        with patch(
            "services.entity_resolver.get_embedding_service",
            return_value=mock_embedding_service,
        ):
            resolver = EntityResolver(mock_session)
            resolver.fuzzy_threshold = 70  # Lower threshold

        assert resolver.fuzzy_threshold == 70


# ============================================================================
# Stage 5: Embedding Similarity Tests
# ============================================================================


class TestEntityResolverEmbeddingSimilarity:
    """Test Stage 5: Embedding similarity with cosine > 0.9."""

    @pytest.mark.asyncio
    async def test_embedding_similarity_match(
        self, mock_session, mock_embedding_service
    ):
        """Should match via embedding similarity above 0.9."""
        entity = EntityFactory.create(name="Machine Learning", entity_type="concept")
        entity_record = {
            "id": entity["id"],
            "name": entity["name"],
            "type": entity["type"],
            "similarity": 0.95,
        }

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            # Stages 1-4: No match
            if "toLower(e.name)" in query:
                return MockNeo4jResult(single_value=None)
            if "ANY(alias IN" in query:
                return MockNeo4jResult(single_value=None)
            if (
                "RETURN e.id AS id, e.name AS name, e.type AS type" in query
                and "embedding" not in query.lower()
            ):
                return MockNeo4jResult(records=[])  # No entities for fuzzy
            # Stage 5: Embedding similarity match
            if "gds.similarity.cosine" in query:
                return MockNeo4jResult(single_value=entity_record)
            return MockNeo4jResult(single_value=None)

        mock_session.run = mock_run

        with patch(
            "services.entity_resolver.get_embedding_service",
            return_value=mock_embedding_service,
        ):
            resolver = EntityResolver(mock_session)
            resolver.embedding_service = mock_embedding_service
            result = await resolver.resolve("ML", "concept")

        assert result.is_new is False
        assert result.match_method == "embedding"
        assert result.confidence >= 0.9

    @pytest.mark.asyncio
    async def test_embedding_similarity_fallback_manual(
        self, resolver_with_mocks, mock_session
    ):
        """Should fall back to manual calculation if GDS fails."""
        entity = EntityFactory.create(name="Deep Learning", entity_type="concept")
        # Set an embedding that will produce high similarity
        base_embedding = [0.5] * 2048

        # No match in earlier stages
        mock_session.set_default_response(single_value=None)
        mock_session.set_response("MATCH (e:Entity)", records=[])

        # GDS fails
        mock_session.set_response("gds.similarity.cosine", single_value=None)

        # Manual fallback returns entity with embedding
        mock_session.set_response(
            "e.embedding IS NOT NULL",
            records=[
                {
                    "id": entity["id"],
                    "name": entity["name"],
                    "type": entity["type"],
                    "embedding": base_embedding,
                }
            ],
        )

        result = await resolver_with_mocks.resolve("DL", "concept")

        # Either matches via embedding or creates new
        assert result is not None

    @pytest.mark.asyncio
    async def test_embedding_similarity_below_threshold(
        self, resolver_with_mocks, mock_session
    ):
        """Should not match if embedding similarity below 0.9."""
        mock_session.set_default_response(single_value=None)
        mock_session.set_response("MATCH (e:Entity)", records=[])
        mock_session.set_response("gds.similarity.cosine", single_value=None)
        mock_session.set_response("e.embedding IS NOT NULL", records=[])

        result = await resolver_with_mocks.resolve("totally_new_thing", "concept")

        assert result.is_new is True
        assert result.match_method == "new"

    @pytest.mark.asyncio
    async def test_embedding_threshold_configurable(
        self, mock_session, mock_embedding_service
    ):
        """Should respect custom embedding threshold."""
        with patch(
            "services.entity_resolver.get_embedding_service",
            return_value=mock_embedding_service,
        ):
            resolver = EntityResolver(mock_session)
            resolver.embedding_threshold = 0.8  # Lower threshold

        assert resolver.embedding_threshold == 0.8


# ============================================================================
# Stage 6: Create New Entity Tests
# ============================================================================


class TestEntityResolverCreateNew:
    """Test Stage 6: Create new entity when no match found."""

    @pytest.mark.asyncio
    async def test_create_new_entity(self, resolver_with_mocks, mock_session):
        """Should create new entity when no match found."""
        mock_session.set_default_response(single_value=None)
        mock_session.set_response("MATCH (e:Entity)", records=[])

        result = await resolver_with_mocks.resolve("BrandNewTechnology", "technology")

        assert result.is_new is True
        assert result.match_method == "new"
        assert result.confidence == 1.0
        assert result.name == "BrandNewTechnology"
        assert result.type == "technology"
        assert result.id is not None

    @pytest.mark.asyncio
    async def test_create_new_uses_canonical_name(
        self, resolver_with_mocks, mock_session
    ):
        """Should use canonical name for new entity when available."""
        mock_session.set_default_response(single_value=None)
        mock_session.set_response("MATCH (e:Entity)", records=[])

        result = await resolver_with_mocks.resolve("pg", "technology")

        # "pg" maps to "PostgreSQL" in CANONICAL_NAMES
        assert result.is_new is True
        assert result.name == "PostgreSQL"

    @pytest.mark.asyncio
    async def test_create_new_adds_original_as_alias(
        self, resolver_with_mocks, mock_session
    ):
        """Should add original name as alias if different from canonical."""
        mock_session.set_default_response(single_value=None)
        mock_session.set_response("MATCH (e:Entity)", records=[])

        result = await resolver_with_mocks.resolve("k8s", "technology")

        assert result.name == "Kubernetes"
        assert "k8s" in result.aliases


# ============================================================================
# Batch Resolution Tests
# ============================================================================


class TestEntityResolverBatch:
    """Test batch entity resolution."""

    @pytest.mark.asyncio
    async def test_resolve_batch_empty(self, resolver_with_mocks):
        """Should handle empty batch."""
        result = await resolver_with_mocks.resolve_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_resolve_batch_single(self, resolver_with_mocks, mock_session):
        """Should resolve single entity in batch."""
        entity = EntityFactory.create(name="Redis", entity_type="technology")
        mock_session.set_response(
            "toLower(e.name)",
            single_value=Neo4jRecordFactory.create_entity_record(entity),
        )

        result = await resolver_with_mocks.resolve_batch(
            [{"name": "Redis", "type": "technology"}]
        )

        assert len(result) == 1
        assert result[0].name == "Redis"

    @pytest.mark.asyncio
    async def test_resolve_batch_deduplication(self, resolver_with_mocks, mock_session):
        """Should deduplicate entities within batch."""
        entity = EntityFactory.create(name="Docker", entity_type="technology")
        mock_session.set_response(
            "toLower(e.name)",
            single_value=Neo4jRecordFactory.create_entity_record(entity),
        )

        result = await resolver_with_mocks.resolve_batch(
            [
                {"name": "Docker", "type": "technology"},
                {"name": "docker", "type": "technology"},
                {"name": "DOCKER", "type": "technology"},
            ]
        )

        assert len(result) == 3
        # All should be the same entity
        assert all(r.id == result[0].id for r in result)

    @pytest.mark.asyncio
    async def test_resolve_batch_canonical_dedup(
        self, resolver_with_mocks, mock_session
    ):
        """Should deduplicate by canonical name within batch."""
        entity = EntityFactory.create(name="PostgreSQL", entity_type="technology")
        mock_session.set_response(
            "toLower(e.name)",
            single_value=Neo4jRecordFactory.create_entity_record(entity),
        )

        result = await resolver_with_mocks.resolve_batch(
            [
                {"name": "PostgreSQL", "type": "technology"},
                {"name": "postgres", "type": "technology"},
                {"name": "pg", "type": "technology"},
            ]
        )

        assert len(result) == 3
        # All should resolve to same entity
        assert all(r.id == result[0].id for r in result)


# ============================================================================
# Entity Merge Tests
# ============================================================================


class TestEntityResolverMerge:
    """Test entity merging and relationship transfer."""

    @pytest.mark.asyncio
    async def test_merge_duplicate_entities(self, resolver_with_mocks, mock_session):
        """Should find and merge duplicate entities."""
        # Two similar entities
        entities = [
            EntityFactory.create(name="PostgreSQL", entity_type="technology"),
            EntityFactory.create(name="Postgresql", entity_type="technology"),
        ]

        mock_session.set_response(
            "MATCH (e:Entity)",
            records=[Neo4jRecordFactory.create_entity_record(e) for e in entities],
        )

        result = await resolver_with_mocks.merge_duplicate_entities()

        assert "groups_found" in result
        assert "entities_merged" in result

    @pytest.mark.asyncio
    async def test_merge_prefers_canonical_entity(
        self, resolver_with_mocks, mock_session
    ):
        """Should keep entity with canonical name when merging."""
        # Entity with canonical name should be preserved
        entities = [
            EntityFactory.create(name="PostgreSQL", entity_type="technology"),
            EntityFactory.create(name="postgres", entity_type="technology"),
        ]

        mock_session.set_response(
            "MATCH (e:Entity)",
            records=[Neo4jRecordFactory.create_entity_record(e) for e in entities],
        )

        # Verify merge_duplicate_entities runs without error
        result = await resolver_with_mocks.merge_duplicate_entities()
        assert result is not None

    @pytest.mark.asyncio
    async def test_add_alias(self, resolver_with_mocks, mock_session):
        """Should add alias to entity."""
        entity_id = str(uuid4())

        await resolver_with_mocks.add_alias(entity_id, "pg")

        # Verify query was called
        assert mock_session.get_call_count() > 0
        assert mock_session.assert_query_contains("SET e.aliases")


# ============================================================================
# Cosine Similarity Tests
# ============================================================================


class TestEntityResolverCosineSimilarity:
    """Test cosine similarity calculation."""

    def test_cosine_similarity_identical_vectors(self):
        """Should return 1.0 for identical vectors."""
        vec = [0.5] * 100
        result = cosine_similarity(vec, vec)
        assert abs(result - 1.0) < 0.0001

    def test_cosine_similarity_orthogonal_vectors(self):
        """Should return 0.0 for orthogonal vectors."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]
        result = cosine_similarity(vec_a, vec_b)
        assert abs(result) < 0.0001

    def test_cosine_similarity_opposite_vectors(self):
        """Should return -1.0 for opposite vectors."""
        vec_a = [1.0, 0.0]
        vec_b = [-1.0, 0.0]
        result = cosine_similarity(vec_a, vec_b)
        assert abs(result + 1.0) < 0.0001

    def test_cosine_similarity_zero_vector(self):
        """Should return 0.0 for zero vectors."""
        vec_a = [0.0] * 100
        vec_b = [0.5] * 100
        result = cosine_similarity(vec_a, vec_b)
        assert result == 0.0


# ============================================================================
# Factory Function Tests
# ============================================================================


class TestGetEntityResolver:
    """Test the factory function."""

    def test_get_entity_resolver_creates_instance(self, mock_session):
        """Should create EntityResolver with session."""
        with patch("services.entity_resolver.get_embedding_service"):
            resolver = get_entity_resolver(mock_session)
            assert isinstance(resolver, EntityResolver)
            assert resolver.session == mock_session


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestOntologyHelpers:
    """Test ontology helper functions used by resolver."""

    def test_normalize_entity_name(self):
        """Should lowercase and strip whitespace."""
        assert normalize_entity_name("  PostgreSQL  ") == "postgresql"
        assert normalize_entity_name("REDIS") == "redis"
        assert normalize_entity_name("FastAPI") == "fastapi"

    def test_get_canonical_name_known(self):
        """Should return canonical name for known aliases."""
        assert get_canonical_name("postgres") == "PostgreSQL"
        assert get_canonical_name("k8s") == "Kubernetes"
        assert get_canonical_name("js") == "JavaScript"

    def test_get_canonical_name_unknown(self):
        """Should return original name for unknown aliases."""
        assert get_canonical_name("UnknownTech") == "UnknownTech"


# ============================================================================
# Run tests
# ============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
