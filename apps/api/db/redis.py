"""Redis connection with configurable connection pooling and retry logic (SD-009).

Pool configuration via environment variables:
- REDIS_POOL_MAX_SIZE: Maximum connections (default: 10)
- REDIS_SOCKET_TIMEOUT: Socket timeout in seconds (default: 5)

Retry configuration:
- REDIS_MAX_RETRIES: Maximum retry attempts (default: 3)
- REDIS_RETRY_DELAY: Base delay for exponential backoff (default: 0.5)
"""

import asyncio
import random
from typing import Any, Callable, TypeVar

import redis.asyncio as redis
from redis.exceptions import (
    BusyLoadingError,
    ReadOnlyError,
)
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
)
from redis.exceptions import (
    TimeoutError as RedisTimeoutError,
)

from config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

redis_client = None

T = TypeVar("T")

# Exceptions that should trigger a retry (SD-009)
REDIS_RETRYABLE_EXCEPTIONS = (
    RedisConnectionError,  # Connection lost
    RedisTimeoutError,  # Operation timeout
    BusyLoadingError,  # Redis is loading data
    ReadOnlyError,  # Replica is read-only (during failover)
    ConnectionError,  # Socket-level errors
    TimeoutError,  # General timeouts
    OSError,  # Low-level I/O errors
)


def _calculate_backoff(
    attempt: int, base_delay: float = 0.5, max_delay: float = 4.0
) -> float:
    """Calculate exponential backoff with jitter (SD-009).

    Args:
        attempt: Current retry attempt (0-indexed)
        base_delay: Base delay in seconds (shorter for Redis as it's faster)
        max_delay: Maximum delay cap

    Returns:
        Delay in seconds with jitter
    """
    delay = min(base_delay * (2**attempt), max_delay)
    # Add jitter to prevent thundering herd
    jitter = random.uniform(0, 0.5)
    return delay + jitter


def _is_retryable_error(exc: Exception) -> bool:
    """Check if an exception should trigger a retry (SD-009).

    Args:
        exc: The exception that was raised

    Returns:
        True if the error is transient and should be retried
    """
    return isinstance(exc, REDIS_RETRYABLE_EXCEPTIONS)


async def with_retry(
    operation: Callable[..., T],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 0.5,
    operation_name: str = "Redis operation",
    **kwargs: Any,
) -> T:
    """Execute an async operation with retry logic (SD-009).

    Args:
        operation: Async callable to execute
        *args: Positional arguments for the operation
        max_retries: Maximum number of retry attempts
        base_delay: Base delay for exponential backoff
        operation_name: Name for logging purposes
        **kwargs: Keyword arguments for the operation

    Returns:
        Result of the operation

    Raises:
        The last exception if all retries are exhausted
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await operation(*args, **kwargs)
        except Exception as e:
            last_exception = e

            if not _is_retryable_error(e):
                logger.error(
                    f"Non-retryable error in {operation_name}: {type(e).__name__}: {e}"
                )
                raise

            if attempt >= max_retries:
                logger.error(
                    f"{operation_name} failed after {max_retries + 1} attempts. "
                    f"Last error: {type(e).__name__}: {e}"
                )
                raise

            delay = _calculate_backoff(attempt, base_delay)
            logger.warning(
                f"{operation_name} attempt {attempt + 1}/{max_retries + 1} failed: "
                f"{type(e).__name__}: {e}. Retrying in {delay:.2f}s"
            )
            await asyncio.sleep(delay)

    # Should never reach here
    if last_exception:
        raise last_exception
    raise RuntimeError(f"Unexpected state in retry for {operation_name}")


async def init_redis():
    """Initialize Redis connection with configurable pool settings and retry (SD-009)."""
    global redis_client
    settings = get_settings()

    # Get pool settings from environment with defaults
    pool_max_size = getattr(settings, "redis_pool_max_size", 10)
    socket_timeout = getattr(settings, "redis_socket_timeout", 5.0)

    logger.info(
        f"Initializing Redis connection pool: "
        f"max_size={pool_max_size}, socket_timeout={socket_timeout}s"
    )

    redis_client = redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        max_connections=pool_max_size,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_timeout,
    )

    # Test connection with retry (SD-009)
    await with_retry(
        redis_client.ping,
        max_retries=3,
        base_delay=0.5,
        operation_name="Redis connection test",
    )

    logger.info("Redis connection pool initialized successfully")


async def close_redis():
    """Close Redis connection pool."""
    global redis_client
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection pool closed")


def get_redis():
    """Get the Redis client."""
    return redis_client


def get_pool_stats() -> dict:
    """Get current connection pool statistics.

    Note: redis-py's async client pool stats are limited.
    """
    if redis_client is None:
        return {
            "max_size": 0,
            "in_use": 0,
        }

    settings = get_settings()
    pool = redis_client.connection_pool

    return {
        "max_size": getattr(settings, "redis_pool_max_size", 10),
        "in_use": len(pool._in_use_connections)
        if hasattr(pool, "_in_use_connections")
        else 0,
    }


# =============================================================================
# Convenience functions with built-in retry (SD-009)
# =============================================================================


async def redis_get(key: str, default: Any = None) -> Any:
    """Get a value from Redis with retry support."""
    if redis_client is None:
        return default

    async def _get():
        return await redis_client.get(key)

    try:
        result = await with_retry(
            _get,
            max_retries=2,
            base_delay=0.3,
            operation_name=f"redis_get({key})",
        )
        return result if result is not None else default
    except Exception as e:
        logger.warning(f"Redis get failed for key '{key}': {e}")
        return default


async def redis_set(
    key: str,
    value: Any,
    ex: int | None = None,
    px: int | None = None,
    nx: bool = False,
    xx: bool = False,
) -> bool:
    """Set a value in Redis with retry support."""
    if redis_client is None:
        return False

    async def _set():
        return await redis_client.set(key, value, ex=ex, px=px, nx=nx, xx=xx)

    try:
        result = await with_retry(
            _set,
            max_retries=2,
            base_delay=0.3,
            operation_name=f"redis_set({key})",
        )
        return bool(result)
    except Exception as e:
        logger.warning(f"Redis set failed for key '{key}': {e}")
        return False


async def redis_delete(*keys: str) -> int:
    """Delete keys from Redis with retry support."""
    if redis_client is None or not keys:
        return 0

    async def _delete():
        return await redis_client.delete(*keys)

    try:
        return await with_retry(
            _delete,
            max_retries=2,
            base_delay=0.3,
            operation_name=f"redis_delete({', '.join(keys)})",
        )
    except Exception as e:
        logger.warning(f"Redis delete failed for keys '{keys}': {e}")
        return 0
