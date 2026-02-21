"""Comprehensive unit tests for EmbeddingService (SEC-007 compliant).

Tests:
- Single text embedding
- Batch text embedding with batching
- Decision embedding
- Entity embedding
- Semantic search
- Cosine similarity calculation

Target: 80%+ coverage for embeddings.py
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.embeddings import EmbeddingService, get_embedding_service
from utils.vectors import cosine_similarity

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_openai_client():
    """Create a mock OpenAI client."""
    client = AsyncMock()

    # Mock embedding response
    response = MagicMock()
    response.data = [MagicMock()]
    response.data[0].embedding = [0.1] * 2048

    client.embeddings.create = AsyncMock(return_value=response)
    return client


def create_mock_settings():
    """Create mock settings with all required attributes."""
    settings = MagicMock()
    settings.nvidia_embedding_api_key = MagicMock()
    settings.get_nvidia_embedding_api_key = MagicMock(return_value="test-key")
    settings.redis_url = "redis://localhost:6379"
    settings.embedding_cache_ttl = 86400
    settings.embedding_cache_min_text_length = 10
    settings.embedding_batch_size = 32  # SD-QW-002: Default batch size
    return settings


@pytest.fixture
def embedding_service(mock_openai_client):
    """Create EmbeddingService with mock client."""
    with patch("services.embeddings.AsyncOpenAI", return_value=mock_openai_client):
        with patch("services.embeddings.get_settings") as mock_settings:
            mock_settings.return_value = create_mock_settings()
            service = EmbeddingService()
            service.client = mock_openai_client
            # Disable Redis caching for tests
            service._redis = None
            return service


# ============================================================================
# Single Text Embedding Tests
# ============================================================================


class TestEmbedText:
    """Test single text embedding."""

    @pytest.mark.asyncio
    async def test_returns_embedding_vector(
        self, embedding_service, mock_openai_client
    ):
        """Should return embedding vector for text."""
        embedding = await embedding_service.embed_text("Test text")

        assert isinstance(embedding, list)
        assert len(embedding) == 2048
        assert all(isinstance(x, float) for x in embedding)

    @pytest.mark.asyncio
    async def test_calls_api_with_correct_params(
        self, embedding_service, mock_openai_client
    ):
        """Should call API with correct parameters."""
        await embedding_service.embed_text("Sample text", input_type="query")

        mock_openai_client.embeddings.create.assert_called_once()
        call_kwargs = mock_openai_client.embeddings.create.call_args.kwargs
        assert call_kwargs["input"] == ["Sample text"]
        assert call_kwargs["model"] == "nvidia/llama-3.2-nv-embedqa-1b-v2"

    @pytest.mark.asyncio
    async def test_passage_input_type(self, embedding_service, mock_openai_client):
        """Should use passage input type for documents."""
        await embedding_service.embed_text("Document content", input_type="passage")

        call_kwargs = mock_openai_client.embeddings.create.call_args.kwargs
        assert call_kwargs["extra_body"]["input_type"] == "passage"

    @pytest.mark.asyncio
    async def test_query_input_type(self, embedding_service, mock_openai_client):
        """Should use query input type for searches."""
        await embedding_service.embed_text("Search query", input_type="query")

        call_kwargs = mock_openai_client.embeddings.create.call_args.kwargs
        assert call_kwargs["extra_body"]["input_type"] == "query"

    @pytest.mark.asyncio
    async def test_default_input_type_is_passage(
        self, embedding_service, mock_openai_client
    ):
        """Should default to passage input type."""
        await embedding_service.embed_text("Default type text")

        call_kwargs = mock_openai_client.embeddings.create.call_args.kwargs
        assert call_kwargs["extra_body"]["input_type"] == "passage"


# ============================================================================
# Batch Embedding Tests
# ============================================================================


class TestEmbedTexts:
    """Test batch text embedding."""

    @pytest.mark.asyncio
    async def test_returns_list_of_embeddings(
        self, embedding_service, mock_openai_client
    ):
        """Should return list of embedding vectors."""
        # Mock response for batch
        response = MagicMock()
        response.data = [
            MagicMock(embedding=[0.1] * 2048),
            MagicMock(embedding=[0.2] * 2048),
        ]
        mock_openai_client.embeddings.create = AsyncMock(return_value=response)

        texts = ["Text 1", "Text 2"]
        embeddings = await embedding_service.embed_texts(texts)

        assert len(embeddings) == 2
        assert all(len(e) == 2048 for e in embeddings)

    @pytest.mark.asyncio
    async def test_batches_large_requests(self, embedding_service, mock_openai_client):
        """Should batch requests for large text lists."""
        # Create 25 texts with long enough text for caching logic
        texts = [f"Text number {i:04d} is long enough for the cache" for i in range(25)]

        def create_response_with_correct_size(*args, **kwargs):
            batch_input = kwargs.get("input", [])
            response = MagicMock()
            response.data = [
                MagicMock(embedding=[0.1] * 2048) for _ in range(len(batch_input))
            ]
            return response

        mock_openai_client.embeddings.create = AsyncMock(
            side_effect=create_response_with_correct_size
        )

        await embedding_service.embed_texts(texts, batch_size=10)

        # Should have called API 3 times (batches of 10, 10, 5)
        assert mock_openai_client.embeddings.create.call_count == 3

    @pytest.mark.asyncio
    async def test_respects_custom_batch_size(
        self, embedding_service, mock_openai_client
    ):
        """Should use custom batch size."""
        # Use longer texts to exceed min_text_length threshold
        texts = [f"Text number {i:04d} is long enough" for i in range(10)]

        def create_response_with_correct_size(*args, **kwargs):
            batch_input = kwargs.get("input", [])
            response = MagicMock()
            response.data = [
                MagicMock(embedding=[0.1] * 2048) for _ in range(len(batch_input))
            ]
            return response

        mock_openai_client.embeddings.create = AsyncMock(
            side_effect=create_response_with_correct_size
        )

        await embedding_service.embed_texts(texts, batch_size=5)

        # Should have called API 2 times with batch_size=5
        assert mock_openai_client.embeddings.create.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(
        self, embedding_service, mock_openai_client
    ):
        """Should return empty list for empty input."""
        embeddings = await embedding_service.embed_texts([])

        assert embeddings == []
        mock_openai_client.embeddings.create.assert_not_called()


# ============================================================================
# Decision Embedding Tests
# ============================================================================


class TestEmbedDecision:
    """Test decision embedding."""

    @pytest.mark.asyncio
    async def test_combines_decision_fields(
        self, embedding_service, mock_openai_client
    ):
        """Should combine all decision fields for embedding."""
        decision = {
            "trigger": "Need to choose a database",
            "context": "Building a new app",
            "options": ["PostgreSQL", "MongoDB"],
            "decision": "PostgreSQL",
            "rationale": "Better for relational data",
        }

        await embedding_service.embed_decision(decision)

        call_kwargs = mock_openai_client.embeddings.create.call_args.kwargs
        input_text = call_kwargs["input"][0]

        assert "Need to choose a database" in input_text
        assert "Building a new app" in input_text
        assert "PostgreSQL" in input_text
        assert "Better for relational data" in input_text

    @pytest.mark.asyncio
    async def test_handles_missing_fields(self, embedding_service, mock_openai_client):
        """Should handle decisions with missing optional fields."""
        decision = {
            "trigger": "Simple decision",
            "decision": "Done",
        }

        embedding = await embedding_service.embed_decision(decision)

        assert len(embedding) == 2048

    @pytest.mark.asyncio
    async def test_uses_passage_type(self, embedding_service, mock_openai_client):
        """Should use passage input type for decisions."""
        decision = {"trigger": "Test", "decision": "Test"}

        await embedding_service.embed_decision(decision)

        call_kwargs = mock_openai_client.embeddings.create.call_args.kwargs
        assert call_kwargs["extra_body"]["input_type"] == "passage"


# ============================================================================
# Entity Embedding Tests
# ============================================================================


class TestEmbedEntity:
    """Test entity embedding."""

    @pytest.mark.asyncio
    async def test_formats_entity_text(self, embedding_service, mock_openai_client):
        """Should format entity with type and name."""
        entity = {"name": "PostgreSQL", "type": "technology"}

        await embedding_service.embed_entity(entity)

        call_kwargs = mock_openai_client.embeddings.create.call_args.kwargs
        input_text = call_kwargs["input"][0]

        assert "technology" in input_text
        assert "PostgreSQL" in input_text

    @pytest.mark.asyncio
    async def test_default_type_is_concept(self, embedding_service, mock_openai_client):
        """Should default to 'concept' for missing type."""
        entity = {"name": "Unknown"}

        await embedding_service.embed_entity(entity)

        call_kwargs = mock_openai_client.embeddings.create.call_args.kwargs
        input_text = call_kwargs["input"][0]

        assert "concept" in input_text

    @pytest.mark.asyncio
    async def test_returns_embedding_vector(self, embedding_service):
        """Should return 2048-dimension embedding."""
        entity = {"name": "Test", "type": "technology"}

        embedding = await embedding_service.embed_entity(entity)

        assert len(embedding) == 2048


# ============================================================================
# Semantic Search Tests
# ============================================================================


class TestSemanticSearch:
    """Test semantic search functionality."""

    @pytest.mark.asyncio
    async def test_returns_top_k_results(self, embedding_service, mock_openai_client):
        """Should return top k most similar candidates."""
        # Create candidates with embeddings
        candidates = [
            {"id": "1", "text": "PostgreSQL", "embedding": [0.9] * 2048},
            {"id": "2", "text": "MongoDB", "embedding": [0.5] * 2048},
            {"id": "3", "text": "Redis", "embedding": [0.7] * 2048},
        ]

        # Mock query embedding that's similar to candidate 1
        response = MagicMock()
        response.data = [MagicMock(embedding=[0.9] * 2048)]
        mock_openai_client.embeddings.create = AsyncMock(return_value=response)

        results = await embedding_service.semantic_search(
            "PostgreSQL", candidates, top_k=2
        )

        assert len(results) == 2
        # Results should be ordered by similarity
        assert results[0]["similarity"] >= results[1]["similarity"]

    @pytest.mark.asyncio
    async def test_includes_similarity_score(
        self, embedding_service, mock_openai_client
    ):
        """Should include similarity score in results."""
        candidates = [
            {"id": "1", "text": "Test", "embedding": [0.5] * 2048},
        ]

        response = MagicMock()
        response.data = [MagicMock(embedding=[0.5] * 2048)]
        mock_openai_client.embeddings.create = AsyncMock(return_value=response)

        results = await embedding_service.semantic_search("Test", candidates)

        assert "similarity" in results[0]
        assert 0 <= results[0]["similarity"] <= 1

    @pytest.mark.asyncio
    async def test_skips_candidates_without_embedding(
        self, embedding_service, mock_openai_client
    ):
        """Should skip candidates missing embedding field."""
        candidates = [
            {"id": "1", "text": "Has embedding", "embedding": [0.5] * 2048},
            {"id": "2", "text": "No embedding"},
        ]

        response = MagicMock()
        response.data = [MagicMock(embedding=[0.5] * 2048)]
        mock_openai_client.embeddings.create = AsyncMock(return_value=response)

        results = await embedding_service.semantic_search("Test", candidates)

        assert len(results) == 1
        assert results[0]["id"] == "1"

    @pytest.mark.asyncio
    async def test_uses_query_input_type(self, embedding_service, mock_openai_client):
        """Should use query input type for search query."""
        candidates = [{"id": "1", "embedding": [0.5] * 2048}]

        await embedding_service.semantic_search("Search query", candidates)

        call_kwargs = mock_openai_client.embeddings.create.call_args.kwargs
        assert call_kwargs["extra_body"]["input_type"] == "query"

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty(
        self, embedding_service, mock_openai_client
    ):
        """Should return empty list for no candidates."""
        results = await embedding_service.semantic_search("Query", [])

        assert results == []


# ============================================================================
# Cosine Similarity Tests
# ============================================================================


class TestCosineSimilarity:
    """Test cosine similarity calculation."""

    def test_identical_vectors(self):
        """Should return 1.0 for identical vectors."""
        vec = [0.5, 0.5, 0.5]
        result = cosine_similarity(vec, vec)

        assert abs(result - 1.0) < 0.0001

    def test_orthogonal_vectors(self):
        """Should return 0.0 for orthogonal vectors."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]
        result = cosine_similarity(vec_a, vec_b)

        assert abs(result) < 0.0001

    def test_opposite_vectors(self):
        """Should return -1.0 for opposite vectors."""
        vec_a = [1.0, 0.0]
        vec_b = [-1.0, 0.0]
        result = cosine_similarity(vec_a, vec_b)

        assert abs(result + 1.0) < 0.0001

    def test_zero_vector_returns_zero(self):
        """Should return 0.0 when one vector is zero."""
        vec_a = [0.0, 0.0, 0.0]
        vec_b = [1.0, 2.0, 3.0]
        result = cosine_similarity(vec_a, vec_b)

        assert result == 0.0

    def test_both_zero_vectors(self):
        """Should return 0.0 when both vectors are zero."""
        vec_a = [0.0, 0.0]
        vec_b = [0.0, 0.0]
        result = cosine_similarity(vec_a, vec_b)

        assert result == 0.0

    def test_normalized_vectors(self):
        """Should handle normalized vectors correctly."""
        import math

        # Create a normalized vector
        vec = [1 / math.sqrt(3), 1 / math.sqrt(3), 1 / math.sqrt(3)]
        result = cosine_similarity(vec, vec)

        assert abs(result - 1.0) < 0.0001


# ============================================================================
# Service Configuration Tests
# ============================================================================


class TestServiceConfiguration:
    """Test service configuration and initialization."""

    def test_dimensions_property(self, embedding_service):
        """Should have 2048 dimensions."""
        assert embedding_service.dimensions == 2048

    def test_model_name(self, embedding_service):
        """Should use correct model name."""
        assert embedding_service.model == "nvidia/llama-3.2-nv-embedqa-1b-v2"


# ============================================================================
# Singleton Tests
# ============================================================================


class TestGetEmbeddingService:
    """Test the singleton getter function."""

    def test_returns_embedding_service(self):
        """Should return EmbeddingService instance."""
        # Reset singleton
        import services.embeddings

        services.embeddings._embedding_service = None

        with patch("services.embeddings.AsyncOpenAI"):
            with patch("services.embeddings.get_settings") as mock_settings:
                mock_settings.return_value = create_mock_settings()
                service = get_embedding_service()

        assert isinstance(service, EmbeddingService)

    def test_returns_same_instance(self):
        """Should return same instance on subsequent calls."""
        import services.embeddings

        services.embeddings._embedding_service = None

        with patch("services.embeddings.AsyncOpenAI"):
            with patch("services.embeddings.get_settings") as mock_settings:
                mock_settings.return_value = create_mock_settings()
                service1 = get_embedding_service()
                service2 = get_embedding_service()

        assert service1 is service2


# ============================================================================
# Run tests
# ============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
