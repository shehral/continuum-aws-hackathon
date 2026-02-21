"""Neo4j database connection with configurable connection pooling and retry logic (SD-009).

Pool configuration via environment variables:
- NEO4J_POOL_MAX_SIZE: Maximum connections (default: 50)
- NEO4J_POOL_ACQUISITION_TIMEOUT: Connection acquisition timeout in seconds (default: 60)

Retry configuration:
- NEO4J_MAX_RETRIES: Maximum retry attempts (default: 3)
- NEO4J_RETRY_DELAY: Base delay for exponential backoff (default: 1.0)
"""

import asyncio
import random
from typing import Any, Callable, TypeVar

from neo4j import AsyncGraphDatabase
from neo4j.exceptions import (
    ClientError,
    DatabaseError,
    ServiceUnavailable,
    SessionExpired,
    TransientError,
)

from config import get_settings
from utils.logging import get_logger
from utils.vectors import cosine_similarity

logger = get_logger(__name__)

driver = None

# Embedding dimensions from NVIDIA NV-EmbedQA model
EMBEDDING_DIMENSIONS = 2048

T = TypeVar("T")

# Exceptions that should trigger a retry (SD-009)
# ServiceUnavailable: Neo4j server is temporarily unavailable
# SessionExpired: Session has expired and needs to be recreated
# TransientError: Transient errors that may succeed on retry
NEO4J_RETRYABLE_EXCEPTIONS = (
    ServiceUnavailable,
    SessionExpired,
    TransientError,
    ConnectionError,
    TimeoutError,
    OSError,
)


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
    return isinstance(exc, NEO4J_RETRYABLE_EXCEPTIONS)


async def with_retry(
    operation: Callable[..., T],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
    operation_name: str = "Neo4j operation",
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


async def init_neo4j():
    """Initialize Neo4j connection with configurable pool settings."""
    global driver
    settings = get_settings()

    # Get pool settings from environment with defaults
    pool_max_size = getattr(settings, "neo4j_pool_max_size", 50)
    pool_acquisition_timeout = getattr(settings, "neo4j_pool_acquisition_timeout", 60)

    logger.info(
        f"Initializing Neo4j connection pool: "
        f"max_size={pool_max_size}, acquisition_timeout={pool_acquisition_timeout}s"
    )

    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.get_neo4j_password()),
        max_connection_pool_size=pool_max_size,
        connection_acquisition_timeout=pool_acquisition_timeout,
    )

    # Create constraints and indexes with retry (SD-009)
    async def create_indexes():
        async with driver.session() as session:
            # Constraints
            await session.run(
                "CREATE CONSTRAINT decision_id IF NOT EXISTS FOR (d:DecisionTrace) REQUIRE d.id IS UNIQUE"
            )
            await session.run(
                "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE"
            )
            await session.run(
                "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE"
            )
            await session.run(
                "CREATE CONSTRAINT system_id IF NOT EXISTS FOR (s:System) REQUIRE s.id IS UNIQUE"
            )
            await session.run(
                "CREATE CONSTRAINT technology_id IF NOT EXISTS FOR (t:Technology) REQUIRE t.id IS UNIQUE"
            )
            await session.run(
                "CREATE CONSTRAINT pattern_id IF NOT EXISTS FOR (p:Pattern) REQUIRE p.id IS UNIQUE"
            )

            # Standard indexes
            await session.run(
                "CREATE INDEX decision_created IF NOT EXISTS FOR (d:DecisionTrace) ON (d.created_at)"
            )
            await session.run(
                "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)"
            )
            await session.run(
                "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)"
            )

            # Case-insensitive entity lookup (lowercase name)
            try:
                await session.run(
                    "CREATE INDEX entity_name_lookup IF NOT EXISTS FOR (e:Entity) ON (e.name)"
                )
                logger.info("Created entity_name_lookup index")
            except (ClientError, DatabaseError) as e:
                logger.debug(f"Entity name lookup index skipped: {e}")

            # Entity aliases index for resolution
            try:
                await session.run(
                    "CREATE INDEX entity_aliases IF NOT EXISTS FOR (e:Entity) ON (e.aliases)"
                )
                logger.info("Created entity_aliases index")
            except (ClientError, DatabaseError) as e:
                logger.debug(f"Entity aliases index skipped: {e}")

            # Decision source index for filtering
            try:
                await session.run(
                    "CREATE INDEX decision_source IF NOT EXISTS FOR (d:DecisionTrace) ON (d.source)"
                )
                logger.info("Created decision_source index")
            except (ClientError, DatabaseError) as e:
                logger.debug(f"Decision source index skipped: {e}")

            # KG-P1-6: Composite indexes for common query patterns

            # Decision user_id + source for user-scoped queries by source
            try:
                await session.run(
                    "CREATE INDEX decision_user_source IF NOT EXISTS FOR (d:DecisionTrace) ON (d.user_id, d.source)"
                )
                logger.info("Created decision_user_source composite index")
            except (ClientError, DatabaseError) as e:
                logger.debug(f"Decision user_source index skipped: {e}")

            # Decision user_id + created_at for user timeline queries
            try:
                await session.run(
                    "CREATE INDEX decision_user_created IF NOT EXISTS FOR (d:DecisionTrace) ON (d.user_id, d.created_at)"
                )
                logger.info("Created decision_user_created composite index")
            except (ClientError, DatabaseError) as e:
                logger.debug(f"Decision user_created index skipped: {e}")

            # Entity type + name for type-filtered lookups
            try:
                await session.run(
                    "CREATE INDEX entity_type_name IF NOT EXISTS FOR (e:Entity) ON (e.type, e.name)"
                )
                logger.info("Created entity_type_name composite index")
            except (ClientError, DatabaseError) as e:
                logger.debug(f"Entity type_name index skipped: {e}")

            # Decision source + created_at for time-based source analysis
            try:
                await session.run(
                    "CREATE INDEX decision_source_time IF NOT EXISTS FOR (d:DecisionTrace) ON (d.source, d.created_at)"
                )
                logger.info("Created decision_source_time composite index")
            except (ClientError, DatabaseError) as e:
                logger.debug(f"Decision source_time index skipped: {e}")

            # Index for user_id alone (frequently used in WHERE clauses)
            try:
                await session.run(
                    "CREATE INDEX decision_user_id IF NOT EXISTS FOR (d:DecisionTrace) ON (d.user_id)"
                )
                logger.info("Created decision_user_id index")
            except (ClientError, DatabaseError) as e:
                logger.debug(f"Decision user_id index skipped: {e}")

            # Vector indexes for semantic search (Neo4j 5.11+)
            try:
                await session.run(
                    """
                    CREATE VECTOR INDEX decision_embedding IF NOT EXISTS
                    FOR (d:DecisionTrace)
                    ON d.embedding
                    OPTIONS {
                        indexConfig: {
                            `vector.dimensions`: $dimensions,
                            `vector.similarity_function`: 'cosine'
                        }
                    }
                    """,
                    dimensions=EMBEDDING_DIMENSIONS,
                )
                logger.info("Created decision_embedding vector index")
            except (ClientError, DatabaseError) as e:
                logger.debug(
                    f"Vector index creation skipped (may already exist or Neo4j < 5.11): {e}"
                )

            try:
                await session.run(
                    """
                    CREATE VECTOR INDEX entity_embedding IF NOT EXISTS
                    FOR (e:Entity)
                    ON e.embedding
                    OPTIONS {
                        indexConfig: {
                            `vector.dimensions`: $dimensions,
                            `vector.similarity_function`: 'cosine'
                        }
                    }
                    """,
                    dimensions=EMBEDDING_DIMENSIONS,
                )
                logger.info("Created entity_embedding vector index")
            except (ClientError, DatabaseError) as e:
                logger.debug(f"Vector index creation skipped: {e}")

            # Full-text indexes for hybrid search
            try:
                await session.run(
                    """
                    CREATE FULLTEXT INDEX decision_fulltext IF NOT EXISTS
                    FOR (d:DecisionTrace)
                    ON EACH [d.trigger, d.context, d.agent_decision, d.agent_rationale]
                    """
                )
                logger.info("Created decision_fulltext index")
            except (ClientError, DatabaseError) as e:
                logger.debug(f"Full-text index creation skipped: {e}")

            try:
                await session.run(
                    """
                    CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS
                    FOR (e:Entity)
                    ON EACH [e.name]
                    """
                )
                logger.info("Created entity_fulltext index")
            except (ClientError, DatabaseError) as e:
                logger.debug(f"Full-text index creation skipped: {e}")

    await with_retry(
        create_indexes,
        max_retries=3,
        base_delay=1.0,
        operation_name="Neo4j index creation",
    )

    logger.info("Neo4j connection pool initialized successfully")


async def close_neo4j():
    """Close Neo4j connection pool."""
    global driver
    if driver:
        await driver.close()
        logger.info("Neo4j connection pool closed")


async def get_neo4j_session():
    """Get a Neo4j session from the pool."""
    return driver.session()


def get_pool_stats() -> dict:
    """Get current connection pool statistics.

    Note: Neo4j Python driver doesn't expose detailed pool stats,
    so we return the configured max size and a placeholder for in-use.
    """
    if driver is None:
        return {
            "max_size": 0,
            "in_use": 0,
        }

    settings = get_settings()
    return {
        "max_size": getattr(settings, "neo4j_pool_max_size", 50),
        "in_use": 0,  # Neo4j driver doesn't expose this directly
    }


# =============================================================================
# Helper functions for common queries with retry support (SD-009)
# =============================================================================


async def find_entity_by_name(name: str, session=None) -> dict | None:
    """Find an entity by name (case-insensitive) or alias with retry support."""
    close_session = False
    if session is None:
        session = await get_neo4j_session()
        close_session = True

    async def _query():
        result = await session.run(
            """
            MATCH (e:Entity)
            WHERE toLower(e.name) = toLower($name)
               OR ANY(alias IN COALESCE(e.aliases, []) WHERE toLower(alias) = toLower($name))
            RETURN e.id AS id, e.name AS name, e.type AS type, e.aliases AS aliases
            LIMIT 1
            """,
            name=name,
        )
        record = await result.single()
        return dict(record) if record else None

    try:
        return await with_retry(
            _query,
            max_retries=3,
            base_delay=0.5,
            operation_name=f"find_entity_by_name({name})",
        )
    finally:
        if close_session:
            await session.close()


async def get_all_entity_names(session=None) -> list[dict]:
    """Get all entity names for fuzzy matching with retry support."""
    close_session = False
    if session is None:
        session = await get_neo4j_session()
        close_session = True

    async def _query():
        result = await session.run(
            """
            MATCH (e:Entity)
            RETURN e.id AS id, e.name AS name, e.type AS type
            """
        )
        return [dict(record) async for record in result]

    try:
        return await with_retry(
            _query,
            max_retries=3,
            base_delay=0.5,
            operation_name="get_all_entity_names",
        )
    finally:
        if close_session:
            await session.close()


# SEC-008: Whitelist of allowed order_by fields to prevent injection
ALLOWED_ORDER_BY_FIELDS = frozenset(
    {
        "created_at",
        "trigger",
        "confidence",
        "decision",
        "rationale",
        "source",
        "name",
        "type",
    }
)


def validate_order_by(field: str) -> str:
    """Validate order_by field against whitelist (SEC-008).

    Args:
        field: The field name to validate

    Returns:
        The validated field name

    Raises:
        ValueError: If field is not in the whitelist
    """
    if field not in ALLOWED_ORDER_BY_FIELDS:
        raise ValueError(
            f"Invalid order_by field: '{field}'. "
            f"Allowed fields: {', '.join(sorted(ALLOWED_ORDER_BY_FIELDS))}"
        )
    return field


async def get_decisions_involving_entity(
    entity_name: str, order_by: str = "created_at", session=None
) -> list[dict]:
    """Get all decisions involving an entity, ordered by specified field with retry support."""
    # SEC-008: Validate order_by field
    order_by = validate_order_by(order_by)

    close_session = False
    if session is None:
        session = await get_neo4j_session()
        close_session = True

    async def _query():
        result = await session.run(
            f"""
            MATCH (e:Entity)
            WHERE toLower(e.name) = toLower($name)
               OR ANY(alias IN COALESCE(e.aliases, []) WHERE toLower(alias) = toLower($name))
            WITH e
            MATCH (d:DecisionTrace)-[:INVOLVES]->(e)
            RETURN d.id AS id,
                   d.trigger AS trigger,
                   COALESCE(d.agent_decision, d.decision) AS decision,
                   COALESCE(d.agent_rationale, d.rationale) AS rationale,
                   d.created_at AS created_at,
                   d.source AS source
            ORDER BY d.{order_by} ASC
            """,
            name=entity_name,
        )
        return [dict(record) async for record in result]

    try:
        return await with_retry(
            _query,
            max_retries=3,
            base_delay=0.5,
            operation_name=f"get_decisions_involving_entity({entity_name})",
        )
    finally:
        if close_session:
            await session.close()


async def find_similar_entity_by_embedding(
    embedding: list[float], threshold: float = 0.9, session=None
) -> dict | None:
    """Find an entity by embedding similarity with retry support."""
    close_session = False
    if session is None:
        session = await get_neo4j_session()
        close_session = True

    async def _query():
        # Try using GDS cosine similarity
        try:
            result = await session.run(
                """
                MATCH (e:Entity)
                WHERE e.embedding IS NOT NULL
                WITH e, gds.similarity.cosine(e.embedding, $embedding) AS similarity
                WHERE similarity > $threshold
                RETURN e.id AS id, e.name AS name, e.type AS type, similarity
                ORDER BY similarity DESC
                LIMIT 1
                """,
                embedding=embedding,
                threshold=threshold,
            )
            record = await result.single()
            return dict(record) if record else None
        except (ClientError, DatabaseError):
            # Fall back to returning all entities for manual calculation
            result = await session.run(
                """
                MATCH (e:Entity)
                WHERE e.embedding IS NOT NULL
                RETURN e.id AS id, e.name AS name, e.type AS type, e.embedding AS embedding
                """
            )

            best_match = None
            best_similarity = threshold

            async for record in result:
                other_embedding = record["embedding"]
                similarity = cosine_similarity(embedding, other_embedding)
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = {
                        "id": record["id"],
                        "name": record["name"],
                        "type": record["type"],
                        "similarity": similarity,
                    }

            return best_match

    try:
        return await with_retry(
            _query,
            max_retries=3,
            base_delay=0.5,
            operation_name="find_similar_entity_by_embedding",
        )
    finally:
        if close_session:
            await session.close()
