"""Tests for the entity lookup cache (SD-011)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.entity_cache import EntityCache, get_entity_cache


class TestEntityCache:
    """Test the entity cache functionality."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.ping = AsyncMock(return_value=True)
        redis.get = AsyncMock(return_value=None)  # Cache miss by default
        redis.setex = AsyncMock(return_value=True)
        redis.delete = AsyncMock(return_value=1)
        redis.scan = AsyncMock(return_value=(0, []))
        redis.close = AsyncMock()
        return redis

    @pytest.fixture
    def sample_entity(self):
        """Return a sample entity for testing."""
        return {
            "id": "test-entity-123",
            "name": "PostgreSQL",
            "type": "technology",
        }

    def test_cache_key_format(self):
        """Should generate correct cache key format."""
        cache = EntityCache()
        key = cache._get_cache_key("user-123", "exact", "PostgreSQL")

        # Key should include user_id, lookup_type, and normalized name
        assert key == "entity:user-123:exact:postgresql"

    def test_cache_key_normalization(self):
        """Should normalize entity names to lowercase."""
        cache = EntityCache()

        key1 = cache._get_cache_key("user-123", "exact", "PostgreSQL")
        key2 = cache._get_cache_key("user-123", "exact", "postgresql")
        key3 = cache._get_cache_key("user-123", "exact", "POSTGRESQL")

        assert key1 == key2 == key3

    def test_cache_key_different_users(self):
        """Should generate different keys for different users."""
        cache = EntityCache()

        key1 = cache._get_cache_key("user-123", "exact", "PostgreSQL")
        key2 = cache._get_cache_key("user-456", "exact", "PostgreSQL")

        assert key1 != key2
        assert "user-123" in key1
        assert "user-456" in key2

    def test_cache_key_different_lookup_types(self):
        """Should generate different keys for different lookup types."""
        cache = EntityCache()

        key_exact = cache._get_cache_key("user-123", "exact", "PostgreSQL")
        key_alias = cache._get_cache_key("user-123", "alias", "PostgreSQL")
        key_id = cache._get_cache_key("user-123", "id", "PostgreSQL")

        assert key_exact != key_alias != key_id

    @pytest.mark.asyncio
    async def test_get_by_exact_name_cache_miss(self, mock_redis):
        """Should return None on cache miss."""
        with patch("services.entity_cache.redis") as mock_redis_module:
            mock_redis_module.from_url = MagicMock(return_value=mock_redis)

            cache = EntityCache()
            result = await cache.get_by_exact_name("user-123", "PostgreSQL")

            assert result is None
            mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_exact_name_cache_hit(self, mock_redis, sample_entity):
        """Should return cached entity on cache hit."""
        mock_redis.get = AsyncMock(return_value=json.dumps(sample_entity))

        with patch("services.entity_cache.redis") as mock_redis_module:
            mock_redis_module.from_url = MagicMock(return_value=mock_redis)

            cache = EntityCache()
            result = await cache.get_by_exact_name("user-123", "PostgreSQL")

            assert result == sample_entity

    @pytest.mark.asyncio
    async def test_set_by_exact_name_caches_entity(self, mock_redis, sample_entity):
        """Should cache entity with configured TTL."""
        with patch("services.entity_cache.redis") as mock_redis_module:
            mock_redis_module.from_url = MagicMock(return_value=mock_redis)

            cache = EntityCache()
            await cache.set_by_exact_name("user-123", "PostgreSQL", sample_entity)

            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args
            assert call_args[0][0] == "entity:user-123:exact:postgresql"
            assert json.loads(call_args[0][2]) == sample_entity

    @pytest.mark.asyncio
    async def test_set_by_exact_name_caches_negative_result(self, mock_redis):
        """Should cache None for negative lookups."""
        with patch("services.entity_cache.redis") as mock_redis_module:
            mock_redis_module.from_url = MagicMock(return_value=mock_redis)

            cache = EntityCache()
            await cache.set_by_exact_name("user-123", "NonExistent", None)

            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args
            assert call_args[0][2] == "null"

    @pytest.mark.asyncio
    async def test_invalidate_entity(self, mock_redis):
        """Should delete cache keys for an entity."""
        with patch("services.entity_cache.redis") as mock_redis_module:
            mock_redis_module.from_url = MagicMock(return_value=mock_redis)

            cache = EntityCache()
            await cache.invalidate_entity(
                "user-123",
                "entity-456",
                entity_name="PostgreSQL",
                aliases=["Postgres", "PG"],
            )

            mock_redis.delete.assert_called_once()
            # Should delete: id key, exact name key, and 2 alias keys
            call_args = mock_redis.delete.call_args
            assert len(call_args[0]) == 4

    @pytest.mark.asyncio
    async def test_invalidate_user_cache(self, mock_redis):
        """Should delete all cache keys for a user."""
        mock_redis.scan = AsyncMock(return_value=(0, ["entity:user-123:exact:test"]))
        mock_redis.delete = AsyncMock(return_value=1)

        with patch("services.entity_cache.redis") as mock_redis_module:
            mock_redis_module.from_url = MagicMock(return_value=mock_redis)

            cache = EntityCache()
            await cache.invalidate_user_cache("user-123")

            mock_redis.scan.assert_called()
            mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_disabled(self):
        """Should return None when cache is disabled."""
        with patch("services.entity_cache.get_settings") as mock_settings:
            mock_settings.return_value.entity_cache_enabled = False
            mock_settings.return_value.redis_url = "redis://localhost:6379"

            cache = EntityCache()
            result = await cache.get_by_exact_name("user-123", "PostgreSQL")

            assert result is None

    @pytest.mark.asyncio
    async def test_redis_connection_failure_graceful(self):
        """Should work gracefully when Redis is unavailable."""
        with patch("services.entity_cache.redis") as mock_redis_module:
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(side_effect=Exception("Connection refused"))
            mock_redis_module.from_url = MagicMock(return_value=mock_redis)

            cache = EntityCache()
            result = await cache.get_by_exact_name("user-123", "PostgreSQL")

            # Should return None, not raise an exception
            assert result is None


class TestGetEntityCache:
    """Test the singleton getter."""

    def test_returns_entity_cache_instance(self):
        """Should return an EntityCache instance."""
        cache = get_entity_cache()
        assert isinstance(cache, EntityCache)

    def test_returns_same_instance(self):
        """Should return the same instance on subsequent calls."""
        cache1 = get_entity_cache()
        cache2 = get_entity_cache()
        assert cache1 is cache2


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
