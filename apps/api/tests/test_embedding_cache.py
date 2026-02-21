"""Tests for the embedding cache with Redis."""

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.embeddings import EmbeddingService


class TestEmbeddingCache:
    """Test the embedding cache functionality."""

    @pytest.fixture
    def mock_embedding_response(self):
        """Create a mock embedding API response."""
        response = MagicMock()
        response.data = [MagicMock()]
        response.data[0].embedding = [0.1] * 2048
        return response

    @pytest.fixture
    def mock_batch_embedding_response(self):
        """Create a mock batch embedding API response."""
        response = MagicMock()
        response.data = [
            MagicMock(embedding=[0.1] * 2048),
            MagicMock(embedding=[0.2] * 2048),
            MagicMock(embedding=[0.3] * 2048),
        ]
        return response

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.ping = AsyncMock(return_value=True)
        redis.get = AsyncMock(return_value=None)  # Cache miss by default
        redis.setex = AsyncMock(return_value=True)
        redis.close = AsyncMock()
        return redis

    def test_cache_key_format(self):
        """Should generate correct cache key format."""
        service = EmbeddingService()
        key = service._get_cache_key("test text", "passage")

        # Key should include model, input_type, and hash
        assert key.startswith("emb:nvembed:passage:")
        assert len(key.split(":")) == 4

        # Hash should be MD5
        expected_hash = hashlib.md5("test text".encode("utf-8")).hexdigest()
        assert key.endswith(expected_hash)

    def test_cache_key_different_types(self):
        """Should generate different keys for different input types."""
        service = EmbeddingService()

        key_passage = service._get_cache_key("test", "passage")
        key_query = service._get_cache_key("test", "query")

        assert key_passage != key_query
        assert "passage" in key_passage
        assert "query" in key_query

    @pytest.mark.asyncio
    async def test_embed_text_cache_miss(self, mock_embedding_response, mock_redis):
        """Should call API and cache result on cache miss."""
        with patch("services.embeddings.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(
                return_value=mock_embedding_response
            )
            mock_client_class.return_value = mock_client

            with patch("services.embeddings.redis") as mock_redis_module:
                mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                service = EmbeddingService()
                result = await service.embed_text(
                    "This is a test sentence that is long enough"
                )

                # Should return embedding
                assert len(result) == 2048

                # Should have called API
                mock_client.embeddings.create.assert_called_once()

                # Should have cached result
                mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_text_cache_hit(self, mock_redis):
        """Should return cached result without API call on cache hit."""
        cached_embedding = [0.5] * 2048
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_embedding))

        with patch("services.embeddings.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch("services.embeddings.redis") as mock_redis_module:
                mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                service = EmbeddingService()
                result = await service.embed_text(
                    "This is a test sentence that is long enough"
                )

                # Should return cached embedding
                assert result == cached_embedding

                # Should NOT have called API
                mock_client.embeddings.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_embed_text_skip_cache_short_text(
        self, mock_embedding_response, mock_redis
    ):
        """Should skip caching for very short texts."""
        with patch("services.embeddings.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(
                return_value=mock_embedding_response
            )
            mock_client_class.return_value = mock_client

            with patch("services.embeddings.redis") as mock_redis_module:
                mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                service = EmbeddingService()
                # Text shorter than min_text_length (10 by default)
                result = await service.embed_text("short")

                # Should return embedding
                assert len(result) == 2048

                # Should have called API
                mock_client.embeddings.create.assert_called_once()

                # Should NOT have tried to cache (text too short)
                mock_redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_embed_texts_batch_caching(
        self, mock_batch_embedding_response, mock_redis
    ):
        """Should handle batch caching correctly."""
        # First text is cached, others are not
        mock_redis.get = AsyncMock(
            side_effect=[
                json.dumps([0.9] * 2048),  # First text cached
                None,  # Second text not cached
                None,  # Third text not cached
            ]
        )

        with patch("services.embeddings.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            # API should only be called for uncached texts
            mock_response = MagicMock()
            mock_response.data = [
                MagicMock(embedding=[0.2] * 2048),
                MagicMock(embedding=[0.3] * 2048),
            ]
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch("services.embeddings.redis") as mock_redis_module:
                mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                service = EmbeddingService()
                texts = [
                    "This is the first test sentence",
                    "This is the second test sentence",
                    "This is the third test sentence",
                ]
                results = await service.embed_texts(texts)

                # Should return 3 embeddings
                assert len(results) == 3

                # First embedding should be from cache
                assert results[0] == [0.9] * 2048

                # API should only be called once for the 2 uncached texts
                mock_client.embeddings.create.assert_called_once()
                call_args = mock_client.embeddings.create.call_args
                assert len(call_args.kwargs["input"]) == 2

    @pytest.mark.asyncio
    async def test_embed_text_redis_failure_graceful(self, mock_embedding_response):
        """Should work gracefully when Redis is unavailable."""
        with patch("services.embeddings.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(
                return_value=mock_embedding_response
            )
            mock_client_class.return_value = mock_client

            with patch("services.embeddings.redis") as mock_redis_module:
                # Redis connection fails
                mock_redis = AsyncMock()
                mock_redis.ping = AsyncMock(side_effect=Exception("Connection refused"))
                mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                service = EmbeddingService()
                result = await service.embed_text(
                    "Test text that is long enough to cache"
                )

                # Should still return embedding from API
                assert len(result) == 2048

    @pytest.mark.asyncio
    async def test_cache_ttl_setting(self, mock_embedding_response, mock_redis):
        """Should use configured TTL for cache entries."""
        with patch("services.embeddings.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(
                return_value=mock_embedding_response
            )
            mock_client_class.return_value = mock_client

            with patch("services.embeddings.redis") as mock_redis_module:
                mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                service = EmbeddingService()
                await service.embed_text("This is a test sentence that is long enough")

                # Check that setex was called with the configured TTL
                mock_redis.setex.assert_called_once()
                call_args = mock_redis.setex.call_args
                # TTL should be the second positional argument
                ttl = call_args[0][1]
                # Default is 30 days (86400 * 30)
                assert ttl == 86400 * 30


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
