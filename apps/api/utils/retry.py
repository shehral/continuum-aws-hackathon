"""Retry utilities with exponential backoff for transient failures (SD-009).

This module provides retry decorators for handling transient failures in
database connections and external API calls.

Usage:
    from utils.retry import retry, RetryExhausted

    @retry(
        max_attempts=3,
        backoff_base=1.0,
        backoff_max=8.0,
        retryable_exceptions={ConnectionError, TimeoutError},
    )
    async def flaky_operation():
        ...
"""

import asyncio
import random
from functools import wraps
from typing import Any, Callable, Optional, Set, Type, TypeVar

from utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class RetryExhausted(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, attempts: int, last_exception: Exception):
        self.attempts = attempts
        self.last_exception = last_exception
        super().__init__(
            f"Retry exhausted after {attempts} attempts. "
            f"Last error: {type(last_exception).__name__}: {last_exception}"
        )


def calculate_backoff(
    attempt: int,
    base: float = 1.0,
    max_delay: float = 8.0,
    jitter: bool = True,
) -> float:
    """Calculate exponential backoff with optional jitter.

    Args:
        attempt: Current attempt number (0-indexed)
        base: Base delay in seconds
        max_delay: Maximum delay cap in seconds
        jitter: Whether to add random jitter (0-1s)

    Returns:
        Delay in seconds before next retry
    """
    # Exponential backoff: base * 2^attempt, capped at max_delay
    delay = min(base * (2**attempt), max_delay)

    # Add jitter to prevent thundering herd
    if jitter:
        delay += random.uniform(0, 1)

    return delay


def retry(
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    backoff_max: float = 8.0,
    jitter: bool = True,
    retryable_exceptions: Optional[Set[Type[Exception]]] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable:
    """Decorator for adding retry logic with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts (including first try)
        backoff_base: Base delay in seconds for backoff calculation
        backoff_max: Maximum delay cap in seconds
        jitter: Whether to add random jitter to prevent thundering herd
        retryable_exceptions: Set of exception types to retry (None = all)
        on_retry: Optional callback called before each retry with (exception, attempt)

    Returns:
        Decorated function with retry logic

    Example:
        @retry(max_attempts=3, retryable_exceptions={ConnectionError})
        async def connect_to_db():
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # Check if this exception is retryable
                    if retryable_exceptions is not None:
                        if not any(
                            isinstance(e, exc_type) for exc_type in retryable_exceptions
                        ):
                            # Not retryable, raise immediately
                            raise

                    # Check if we've exhausted attempts
                    if attempt >= max_attempts - 1:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts. "
                            f"Last error: {type(e).__name__}: {e}"
                        )
                        raise

                    # Calculate backoff
                    delay = calculate_backoff(
                        attempt, backoff_base, backoff_max, jitter
                    )

                    # Call retry callback if provided
                    if on_retry:
                        on_retry(e, attempt)

                    logger.warning(
                        f"{func.__name__} attempt {attempt + 1}/{max_attempts} failed: "
                        f"{type(e).__name__}: {e}. Retrying in {delay:.2f}s"
                    )

                    await asyncio.sleep(delay)

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError(f"Unexpected state in retry for {func.__name__}")

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            import time as sync_time

            last_exception: Optional[Exception] = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # Check if this exception is retryable
                    if retryable_exceptions is not None:
                        if not any(
                            isinstance(e, exc_type) for exc_type in retryable_exceptions
                        ):
                            raise

                    if attempt >= max_attempts - 1:
                        raise

                    delay = calculate_backoff(
                        attempt, backoff_base, backoff_max, jitter
                    )

                    if on_retry:
                        on_retry(e, attempt)

                    logger.warning(
                        f"{func.__name__} attempt {attempt + 1}/{max_attempts} failed: "
                        f"{type(e).__name__}: {e}. Retrying in {delay:.2f}s"
                    )

                    sync_time.sleep(delay)

            if last_exception:
                raise last_exception
            raise RuntimeError(f"Unexpected state in retry for {func.__name__}")

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Pre-configured retry decorators for common use cases

# PostgreSQL retryable exceptions
POSTGRES_RETRYABLE = {
    # SQLAlchemy/asyncpg connection errors
    ConnectionError,
    TimeoutError,
    OSError,  # Includes socket errors
}

# Neo4j retryable exceptions
NEO4J_RETRYABLE = {
    # neo4j.exceptions
    ConnectionError,
    TimeoutError,
    OSError,
}

# Redis retryable exceptions
REDIS_RETRYABLE = {
    ConnectionError,
    TimeoutError,
    OSError,
}


def postgres_retry(
    max_attempts: int = 3,
    backoff_base: float = 1.0,
) -> Callable:
    """Decorator with PostgreSQL-specific retry settings."""
    return retry(
        max_attempts=max_attempts,
        backoff_base=backoff_base,
        retryable_exceptions=POSTGRES_RETRYABLE,
    )


def neo4j_retry(
    max_attempts: int = 3,
    backoff_base: float = 1.0,
) -> Callable:
    """Decorator with Neo4j-specific retry settings."""
    return retry(
        max_attempts=max_attempts,
        backoff_base=backoff_base,
        retryable_exceptions=NEO4J_RETRYABLE,
    )


def redis_retry(
    max_attempts: int = 3,
    backoff_base: float = 0.5,
) -> Callable:
    """Decorator with Redis-specific retry settings."""
    return retry(
        max_attempts=max_attempts,
        backoff_base=backoff_base,
        retryable_exceptions=REDIS_RETRYABLE,
    )
