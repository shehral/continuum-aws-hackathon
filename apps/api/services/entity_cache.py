"""Entity lookup cache with Redis (SD-011).

Caches entity lookups to reduce Neo4j query load during entity resolution.
Cache keys include user_id for multi-tenant isolation.

Features:
- 5-minute TTL (configurable via ENTITY_CACHE_TTL)
- Automatic invalidation on entity create/update/delete
- User-scoped caching for multi-tenant support
- Graceful degradation when Redis is unavailable
"""

import json
from typing import Optional

import redis.asyncio as redis

from config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class EntityCache:
    """Redis-based cache for entity lookups (SD-011).

    Cache key format: entity:{user_id}:{lookup_type}:{key}

    Lookup types:
    - exact:{name} - Exact name match
    - alias:{name} - Alias lookup
    - id:{entity_id} - Entity by ID

    Invalidation patterns:
    - entity:{user_id}:* - Invalidate all user's entity cache
    - entity:*:{type}:{key} - Invalidate specific lookup across users
    """

    def __init__(self):
        self._redis: redis.Redis | None = None
        self._settings = get_settings()
        self._enabled = self._settings.entity_cache_enabled

    async def _get_redis(self) -> redis.Redis | None:
        """Get or create Redis connection for caching."""
        if not self._enabled:
            return None

        if self._redis is None:
            try:
                self._redis = redis.from_url(
                    self._settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self._redis.ping()
            except Exception as e:
                logger.warning(f"Entity cache Redis connection failed: {e}")
                self._redis = None
        return self._redis

    def _get_cache_key(self, user_id: str, lookup_type: str, key: str) -> str:
        """Generate a cache key for entity lookup.

        Format: entity:{user_id}:{lookup_type}:{key}
        """
        # Normalize key to lowercase for case-insensitive lookups
        normalized_key = key.lower() if key else ""
        return f"entity:{user_id}:{lookup_type}:{normalized_key}"

    async def get_by_exact_name(self, user_id: str, name: str) -> Optional[dict]:
        """Get cached entity by exact name match."""
        redis_client = await self._get_redis()
        if redis_client is None:
            return None

        try:
            cache_key = self._get_cache_key(user_id, "exact", name)
            cached = await redis_client.get(cache_key)
            if cached:
                logger.debug(f"Entity cache hit: exact name '{name}'")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Entity cache read error: {e}")

        return None

    async def set_by_exact_name(
        self, user_id: str, name: str, entity: dict | None
    ) -> None:
        """Cache entity lookup by exact name.

        Args:
            user_id: User ID for scoping
            name: Entity name (will be normalized to lowercase)
            entity: Entity dict or None for negative cache
        """
        redis_client = await self._get_redis()
        if redis_client is None:
            return

        try:
            cache_key = self._get_cache_key(user_id, "exact", name)
            # Cache both positive and negative results
            value = json.dumps(entity) if entity else json.dumps(None)
            await redis_client.setex(
                cache_key,
                self._settings.entity_cache_ttl,
                value,
            )
            logger.debug(f"Entity cached: exact name '{name}'")
        except Exception as e:
            logger.warning(f"Entity cache write error: {e}")

    async def get_by_alias(self, user_id: str, alias: str) -> Optional[dict]:
        """Get cached entity by alias lookup."""
        redis_client = await self._get_redis()
        if redis_client is None:
            return None

        try:
            cache_key = self._get_cache_key(user_id, "alias", alias)
            cached = await redis_client.get(cache_key)
            if cached:
                logger.debug(f"Entity cache hit: alias '{alias}'")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Entity cache read error: {e}")

        return None

    async def set_by_alias(self, user_id: str, alias: str, entity: dict | None) -> None:
        """Cache entity lookup by alias."""
        redis_client = await self._get_redis()
        if redis_client is None:
            return

        try:
            cache_key = self._get_cache_key(user_id, "alias", alias)
            value = json.dumps(entity) if entity else json.dumps(None)
            await redis_client.setex(
                cache_key,
                self._settings.entity_cache_ttl,
                value,
            )
            logger.debug(f"Entity cached: alias '{alias}'")
        except Exception as e:
            logger.warning(f"Entity cache write error: {e}")

    async def get_by_id(self, user_id: str, entity_id: str) -> Optional[dict]:
        """Get cached entity by ID."""
        redis_client = await self._get_redis()
        if redis_client is None:
            return None

        try:
            cache_key = self._get_cache_key(user_id, "id", entity_id)
            cached = await redis_client.get(cache_key)
            if cached:
                logger.debug(f"Entity cache hit: id '{entity_id}'")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Entity cache read error: {e}")

        return None

    async def set_by_id(self, user_id: str, entity_id: str, entity: dict) -> None:
        """Cache entity by ID."""
        redis_client = await self._get_redis()
        if redis_client is None:
            return

        try:
            cache_key = self._get_cache_key(user_id, "id", entity_id)
            await redis_client.setex(
                cache_key,
                self._settings.entity_cache_ttl,
                json.dumps(entity),
            )
            logger.debug(f"Entity cached: id '{entity_id}'")
        except Exception as e:
            logger.warning(f"Entity cache write error: {e}")

    async def invalidate_entity(
        self,
        user_id: str,
        entity_id: str,
        entity_name: str | None = None,
        aliases: list[str] | None = None,
    ) -> int:
        """Invalidate cache entries for a specific entity.

        Called on entity create/update/delete operations.

        Args:
            user_id: User ID for scoping
            entity_id: Entity ID to invalidate
            entity_name: Entity name (if known) for name-based invalidation
            aliases: Entity aliases (if known) for alias-based invalidation

        Returns:
            Number of keys deleted
        """
        redis_client = await self._get_redis()
        if redis_client is None:
            return 0

        try:
            keys_to_delete = []

            # Always invalidate by ID
            keys_to_delete.append(self._get_cache_key(user_id, "id", entity_id))

            # Invalidate by name if provided
            if entity_name:
                keys_to_delete.append(
                    self._get_cache_key(user_id, "exact", entity_name)
                )

            # Invalidate by aliases if provided
            if aliases:
                for alias in aliases:
                    keys_to_delete.append(self._get_cache_key(user_id, "alias", alias))

            if keys_to_delete:
                deleted = await redis_client.delete(*keys_to_delete)
                logger.debug(
                    f"Entity cache invalidated: {deleted} keys for entity {entity_id}"
                )
                return deleted

            return 0

        except Exception as e:
            logger.warning(f"Entity cache invalidation error: {e}")
            return 0

    async def invalidate_user_cache(self, user_id: str) -> int:
        """Invalidate all cached entities for a user.

        Useful after bulk operations or data migrations.

        Args:
            user_id: User ID whose cache to clear

        Returns:
            Number of keys deleted
        """
        redis_client = await self._get_redis()
        if redis_client is None:
            return 0

        try:
            pattern = f"entity:{user_id}:*"
            deleted = 0

            # Use SCAN to find keys (safer for large datasets)
            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(
                    cursor=cursor, match=pattern, count=100
                )
                if keys:
                    deleted += await redis_client.delete(*keys)
                if cursor == 0:
                    break

            logger.info(f"Entity cache cleared for user: {deleted} keys deleted")
            return deleted

        except Exception as e:
            logger.warning(f"Entity cache user invalidation error: {e}")
            return 0

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()


# Singleton instance
_entity_cache: EntityCache | None = None


def get_entity_cache() -> EntityCache:
    """Get the entity cache singleton."""
    global _entity_cache
    if _entity_cache is None:
        _entity_cache = EntityCache()
    return _entity_cache
