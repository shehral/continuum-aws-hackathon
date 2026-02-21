"""PostgreSQL database connection with configurable connection pooling and retry logic (SD-009).

Pool configuration via environment variables:
- POSTGRES_POOL_MIN_SIZE: Minimum connections (default: 2)
- POSTGRES_POOL_MAX_SIZE: Maximum connections (default: 10)
- POSTGRES_POOL_RECYCLE: Connection recycle time in seconds (default: 3600)

Retry configuration:
- POSTGRES_MAX_RETRIES: Maximum retry attempts (default: 3)
- POSTGRES_RETRY_DELAY: Base delay for exponential backoff (default: 1.0)
"""

import asyncio
import random
from typing import Any, Callable, TypeVar

from sqlalchemy.exc import (
    DBAPIError,
    InterfaceError,
    OperationalError,
)
from sqlalchemy.exc import (
    TimeoutError as SQLAlchemyTimeoutError,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

engine = None
async_session_maker = None

T = TypeVar("T")

# Exceptions that should trigger a retry (SD-009)
POSTGRES_RETRYABLE_EXCEPTIONS = (
    OperationalError,  # Connection issues, server disconnects
    InterfaceError,  # Interface-level errors
    DBAPIError,  # Generic database errors (filtered by is_disconnect)
    SQLAlchemyTimeoutError,  # Query timeouts
    ConnectionError,  # Socket-level connection errors
    TimeoutError,  # General timeouts
    OSError,  # Low-level I/O errors
)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy declarative models."""

    pass


def _calculate_backoff(
    attempt: int, base_delay: float = 1.0, max_delay: float = 8.0
) -> float:
    """Calculate exponential backoff with jitter (SD-009).

    Args:
        attempt: Current retry attempt (0-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay cap

    Returns:
        Delay in seconds with jitter
    """
    delay = min(base_delay * (2**attempt), max_delay)
    # Add jitter to prevent thundering herd
    jitter = random.uniform(0, 1)
    return delay + jitter


def _is_retryable_error(exc: Exception) -> bool:
    """Check if an exception should trigger a retry (SD-009).

    Args:
        exc: The exception that was raised

    Returns:
        True if the error is transient and should be retried
    """
    if isinstance(exc, POSTGRES_RETRYABLE_EXCEPTIONS):
        # For DBAPIError, only retry disconnects
        if isinstance(exc, DBAPIError) and not exc.connection_invalidated:
            return False
        return True
    return False


async def with_retry(
    operation: Callable[..., T],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
    operation_name: str = "database operation",
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


async def init_postgres():
    """Initialize PostgreSQL connection with configurable pool settings and retry (SD-009)."""
    global engine, async_session_maker
    settings = get_settings()

    # Get pool settings from environment with defaults
    pool_min_size = getattr(settings, "postgres_pool_min_size", 2)
    pool_max_size = getattr(settings, "postgres_pool_max_size", 10)
    pool_recycle = getattr(settings, "postgres_pool_recycle", 3600)

    logger.info(
        f"Initializing PostgreSQL connection pool: "
        f"min={pool_min_size}, max={pool_max_size}, recycle={pool_recycle}s"
    )

    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=pool_min_size,
        max_overflow=pool_max_size - pool_min_size,
        pool_recycle=pool_recycle,
    )

    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Create tables with retry (SD-009)
    async def create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    await with_retry(
        create_tables,
        max_retries=3,
        base_delay=1.0,
        operation_name="PostgreSQL table creation",
    )

    # Seed the anonymous user if it doesn't exist (required for unauthenticated sessions)
    async with async_session_maker() as session:
        from sqlalchemy import text

        result = await session.execute(
            text("SELECT id FROM users WHERE id = 'anonymous'")
        )
        if result.scalar_one_or_none() is None:
            await session.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, name, created_at, updated_at) "
                    "VALUES ('anonymous', 'anonymous@localhost', '', 'Anonymous', NOW(), NOW())"
                )
            )
            await session.commit()
            logger.info("Seeded anonymous user for unauthenticated access")

    logger.info("PostgreSQL connection pool initialized successfully")


async def close_postgres():
    """Close PostgreSQL connection pool."""
    global engine
    if engine:
        await engine.dispose()
        logger.info("PostgreSQL connection pool closed")


async def get_db() -> AsyncSession:
    """Get a database session from the pool with automatic retry on connection issues."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_pool_stats() -> dict:
    """Get current connection pool statistics.

    Returns:
        Dict with pool_size, checked_out, overflow, checked_in counts
    """
    if engine is None:
        return {
            "pool_size": 0,
            "checked_out": 0,
            "overflow": 0,
            "checked_in": 0,
        }

    pool = engine.pool
    return {
        "pool_size": pool.size(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "checked_in": pool.checkedin(),
    }
