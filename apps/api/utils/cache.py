"""Redis-based caching utilities for API responses (SD-024).

Provides decorators and utilities for caching expensive query results
with automatic invalidation support.

Usage:
    @cached(key_prefix="dashboard_stats", ttl=30)
    async def get_dashboard_stats(user_id: str):
        ...

Cache keys are constructed as: {prefix}:{user_id}:{hash(args)}
"""

import functools
import hashlib
import json
from typing import Any, Callable, Optional, TypeVar

from db.redis import get_redis
from utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# Cache key prefixes for different endpoints
CACHE_PREFIXES = {
    "dashboard_stats": "cache:dashboard:stats",
    "graph_stats": "cache:graph:stats",
    "graph_sources": "cache:graph:sources",
    "graph_projects": "cache:graph:projects",
    "agent_summary": "cache:agent:summary",
    "agent_context": "cache:agent:context",
    "agent_entity": "cache:agent:entity",
}

# Default TTLs in seconds
DEFAULT_TTLS = {
    "dashboard_stats": 30,  # 30 seconds - changes frequently with new decisions
    "graph_stats": 30,  # 30 seconds - similar to dashboard
    "graph_sources": 60,  # 60 seconds - changes less frequently
    "graph_projects": 60,  # 60 seconds - changes less frequently
    "agent_summary": 120,  # 2 minutes - high-level overview changes slowly
    "agent_context": 30,  # 30 seconds - query-specific cache
    "agent_entity": 60,  # 60 seconds - entity info changes slowly
}


def _build_cache_key(prefix: str, user_id: str, *args: Any, **kwargs: Any) -> str:
    """Build a cache key from prefix, user_id, and function arguments.

    Args:
        prefix: Cache key prefix (e.g., "dashboard_stats")
        user_id: User ID for multi-tenant isolation
        *args: Positional arguments to hash
        **kwargs: Keyword arguments to hash

    Returns:
        Cache key string
    """
    # Create a deterministic hash of the arguments
    arg_data = json.dumps({"args": list(args), "kwargs": kwargs}, sort_keys=True)
    arg_hash = hashlib.md5(arg_data.encode()).hexdigest()[:8]

    full_prefix = CACHE_PREFIXES.get(prefix, f"cache:{prefix}")
    return f"{full_prefix}:{user_id}:{arg_hash}"


async def get_cached(
    prefix: str,
    user_id: str,
    *args: Any,
    **kwargs: Any,
) -> Optional[Any]:
    """Get a cached value.

    Args:
        prefix: Cache key prefix
        user_id: User ID for isolation
        *args, **kwargs: Additional arguments for cache key

    Returns:
        Cached value or None if not found
    """
    redis_client = get_redis()
    if redis_client is None:
        return None

    cache_key = _build_cache_key(prefix, user_id, *args, **kwargs)

    try:
        cached = await redis_client.get(cache_key)
        if cached:
            logger.debug(f"Cache hit: {cache_key}")
            return json.loads(cached)
        logger.debug(f"Cache miss: {cache_key}")
        return None
    except Exception as e:
        logger.warning(f"Cache read error for {cache_key}: {e}")
        return None


async def set_cached(
    prefix: str,
    user_id: str,
    value: Any,
    ttl: Optional[int] = None,
    *args: Any,
    **kwargs: Any,
) -> bool:
    """Set a cached value.

    Args:
        prefix: Cache key prefix
        user_id: User ID for isolation
        value: Value to cache (must be JSON serializable)
        ttl: Time-to-live in seconds (uses default if not specified)
        *args, **kwargs: Additional arguments for cache key

    Returns:
        True if cached successfully, False otherwise
    """
    redis_client = get_redis()
    if redis_client is None:
        return False

    cache_key = _build_cache_key(prefix, user_id, *args, **kwargs)

    # Use default TTL if not specified
    if ttl is None:
        ttl = DEFAULT_TTLS.get(prefix, 60)

    try:
        # Custom JSON encoder to handle datetime objects
        def json_serializer(obj):
            """JSON serializer for objects not serializable by default json code"""
            from datetime import datetime, date
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")
        
        await redis_client.setex(cache_key, ttl, json.dumps(value, default=json_serializer))
        logger.debug(f"Cache set: {cache_key} (TTL: {ttl}s)")
        return True
    except Exception as e:
        logger.warning(f"Cache write error for {cache_key}: {e}")
        return False


async def invalidate_cache(prefix: str, user_id: str) -> int:
    """Invalidate all cache entries for a prefix and user.

    Args:
        prefix: Cache key prefix to invalidate
        user_id: User ID

    Returns:
        Number of keys deleted
    """
    redis_client = get_redis()
    if redis_client is None:
        return 0

    full_prefix = CACHE_PREFIXES.get(prefix, f"cache:{prefix}")
    pattern = f"{full_prefix}:{user_id}:*"

    try:
        # Use SCAN to find matching keys (safer than KEYS for large datasets)
        deleted = 0
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor, match=pattern, count=100)
            if keys:
                deleted += await redis_client.delete(*keys)
            if cursor == 0:
                break

        if deleted > 0:
            logger.info(f"Invalidated {deleted} cache entries for {pattern}")
        return deleted
    except Exception as e:
        logger.warning(f"Cache invalidation error for {pattern}: {e}")
        return 0


async def invalidate_user_caches(user_id: str) -> int:
    """Invalidate all cache entries for a user.

    Call this when user data changes significantly (e.g., after decision creation).

    Args:
        user_id: User ID

    Returns:
        Total number of keys deleted
    """
    total_deleted = 0
    for prefix in CACHE_PREFIXES:
        total_deleted += await invalidate_cache(prefix, user_id)
    return total_deleted


def cached(
    key_prefix: str,
    ttl: Optional[int] = None,
    user_id_param: str = "user_id",
):
    """Decorator for caching async function results (SD-024).

    The decorated function must have a user_id parameter (or specified by user_id_param).

    Args:
        key_prefix: Cache key prefix (e.g., "dashboard_stats")
        ttl: Cache TTL in seconds (uses default if not specified)
        user_id_param: Name of the user_id parameter in the function

    Example:
        @cached(key_prefix="dashboard_stats", ttl=30)
        async def get_dashboard_stats(user_id: str) -> dict:
            # expensive query
            return {"total": 100}
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            # Extract user_id from kwargs or args
            user_id = kwargs.get(user_id_param)
            if user_id is None and args:
                # Try to get from positional args based on function signature
                import inspect

                sig = inspect.signature(func)
                params = list(sig.parameters.keys())
                try:
                    user_id_index = params.index(user_id_param)
                    if user_id_index < len(args):
                        user_id = args[user_id_index]
                except (ValueError, IndexError):
                    pass

            if user_id is None:
                # Can't cache without user_id, execute directly
                logger.warning(f"Cannot cache {func.__name__}: no user_id found")
                return await func(*args, **kwargs)

            # Build cache key from remaining args (exclude user_id)
            cache_args = (
                [
                    a
                    for i, a in enumerate(args)
                    if i
                    != (params.index(user_id_param) if user_id_param in params else -1)
                ]
                if "params" in dir()
                else list(args)
            )
            cache_kwargs = {k: v for k, v in kwargs.items() if k != user_id_param}

            # Try to get from cache
            cached_value = await get_cached(
                key_prefix, user_id, *cache_args, **cache_kwargs
            )
            if cached_value is not None:
                return cached_value

            # Execute function and cache result
            result = await func(*args, **kwargs)

            # Only cache non-None results
            if result is not None:
                # Convert Pydantic models to dict if needed
                cache_value = result
                if hasattr(result, "model_dump"):
                    cache_value = result.model_dump()
                elif hasattr(result, "dict"):
                    cache_value = result.dict()

                await set_cached(
                    key_prefix,
                    user_id,
                    cache_value,
                    ttl,
                    *cache_args,
                    **cache_kwargs,
                )

            return result

        return wrapper

    return decorator
