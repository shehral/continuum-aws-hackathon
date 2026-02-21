"""FastAPI application with security middleware and standardized error handling.

Features:
- SEC-010: Request size limits
- SEC-011: Restricted CORS configuration
- SD-016: Standardized error response schema
- SD-006: Circuit breaker integration
- SD-021: Response compression (GZip)
- DEVOPS-P2-1: Security headers middleware
- DEVOPS-QW-5: Structured startup logging
"""

import asyncio
import os
import platform
import signal
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import get_settings
from db.neo4j import close_neo4j, init_neo4j
from db.postgres import close_postgres, init_postgres
from db.redis import close_redis, get_redis, init_redis
from middleware.request_size import RequestSizeLimitMiddleware
from middleware.security import SecurityHeadersMiddleware
from models.errors import (
    ErrorType,
    create_error_response,
    create_validation_error_response,
)
from routers import (
    agent,
    analytics,
    capture,
    dashboard,
    decisions,
    entities,
    export,
    git,
    graph,
    ingest,
    notifications,
    projects,
    search,
    users,
)
from utils.circuit_breaker import CircuitBreakerOpen, get_circuit_breaker_stats
from utils.logging import get_logger

# Application version - update this when releasing new versions
APP_VERSION = "0.1.0"
APP_NAME = "Continuum API"

logger = get_logger(__name__)

# Global shutdown event for coordinating graceful shutdown
shutdown_event = asyncio.Event()


def get_request_id(request: Request) -> str | None:
    """Extract request ID from request state or headers."""
    if hasattr(request.state, "request_id"):
        return request.state.request_id
    return request.headers.get("X-Request-ID")


async def check_postgres_connection() -> bool:
    """Verify PostgreSQL connection is healthy."""
    from db.postgres import engine

    if engine is None:
        return False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {e}")
        return False


async def check_neo4j_connection() -> bool:
    """Verify Neo4j connection is healthy."""
    from db.neo4j import driver

    if driver is None:
        return False
    try:
        async with driver.session() as session:
            await session.run("RETURN 1")
        return True
    except Exception as e:
        logger.error(f"Neo4j health check failed: {e}")
        return False


async def check_redis_connection() -> bool:
    """Verify Redis connection is healthy."""
    client = get_redis()
    if client is None:
        return False
    try:
        await client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False


async def init_databases() -> dict[str, bool]:
    """Initialize all database connections with error handling."""
    services_status = {"postgres": False, "neo4j": False, "redis": False}

    # Initialize PostgreSQL
    try:
        await init_postgres()
        services_status["postgres"] = True
        logger.info("PostgreSQL connection established")
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        raise

    # Initialize Neo4j
    try:
        await init_neo4j()
        services_status["neo4j"] = True
        logger.info("Neo4j connection established")
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j: {e}")
        # Close PostgreSQL if Neo4j fails
        await close_postgres()
        raise

    # Initialize Redis
    try:
        await init_redis()
        services_status["redis"] = True
        logger.info("Redis connection established")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        # Close other connections if Redis fails
        await close_postgres()
        await close_neo4j()
        raise

    return services_status


async def close_databases():
    """Close all database connections gracefully."""
    errors = []

    # Close Redis first (typically fastest)
    try:
        await close_redis()
        logger.info("Redis connection closed")
    except Exception as e:
        errors.append(f"Redis: {e}")
        logger.error(f"Error closing Redis: {e}")

    # Close Neo4j
    try:
        await close_neo4j()
        logger.info("Neo4j connection closed")
    except Exception as e:
        errors.append(f"Neo4j: {e}")
        logger.error(f"Error closing Neo4j: {e}")

    # Close PostgreSQL last
    try:
        await close_postgres()
        logger.info("PostgreSQL connection closed")
    except Exception as e:
        errors.append(f"PostgreSQL: {e}")
        logger.error(f"Error closing PostgreSQL: {e}")

    if errors:
        logger.warning(f"Errors during database shutdown: {errors}")


def setup_signal_handlers(loop: asyncio.AbstractEventLoop):
    """Set up signal handlers for graceful shutdown."""

    def signal_handler(sig):
        sig_name = signal.Signals(sig).name
        logger.info(f"Received {sig_name}, initiating graceful shutdown...")
        shutdown_event.set()

    # Register signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
            logger.debug(f"Registered handler for {signal.Signals(sig).name}")
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            signal.signal(sig, lambda s, f, sig=sig: signal_handler(sig))
            logger.debug(
                f"Registered signal handler for {signal.Signals(sig).name} (fallback)"
            )


def log_startup_banner(settings, services_status: dict[str, bool]):
    """Log structured startup information (DEVOPS-QW-5).

    Logs application version, environment, connected services, and runtime info
    in a structured format suitable for log aggregation systems.
    """
    # Determine environment
    environment = "development" if settings.debug else "production"

    # Get port from environment or default
    port = int(os.getenv("PORT", os.getenv("UVICORN_PORT", "8000")))
    host = os.getenv("HOST", os.getenv("UVICORN_HOST", "127.0.0.1"))

    # Build services status summary
    connected_services = [svc for svc, ok in services_status.items() if ok]
    failed_services = [svc for svc, ok in services_status.items() if not ok]

    # Log structured startup information
    logger.info(
        "Application startup complete",
        extra={
            "event": "startup",
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "environment": environment,
            "host": host,
            "port": port,
            "python_version": platform.python_version(),
            "platform": platform.system(),
            "services": {
                "connected": connected_services,
                "failed": failed_services,
                "postgres": "connected"
                if services_status.get("postgres")
                else "failed",
                "neo4j": "connected" if services_status.get("neo4j") else "failed",
                "redis": "connected" if services_status.get("redis") else "failed",
            },
            "config": {
                "cors_origins": settings.cors_origins,
                "rate_limit_requests": settings.rate_limit_requests,
                "rate_limit_window": settings.rate_limit_window,
                "llm_model": settings.nvidia_model,
                "embedding_model": settings.nvidia_embedding_model,
            },
        },
    )

    # Also log human-readable summary for local development
    logger.info(f"App: {APP_NAME} v{APP_VERSION}")
    logger.info(f"Environment: {environment}")
    logger.info(f"Listening on: http://{host}:{port}")
    logger.info(f"Python: {platform.python_version()} ({platform.system()})")
    logger.info(f"Services connected: {', '.join(connected_services) or 'none'}")
    if failed_services:
        logger.warning(f"Services failed: {', '.join(failed_services)}")
    logger.info(f"API docs available at: http://{host}:{port}/docs")


def log_shutdown_info():
    """Log structured shutdown information."""
    logger.info(
        "Application shutdown initiated",
        extra={
            "event": "shutdown",
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager with graceful shutdown support."""
    settings = get_settings()

    # Set up signal handlers
    try:
        loop = asyncio.get_running_loop()
        setup_signal_handlers(loop)
    except Exception as e:
        logger.warning(f"Could not set up signal handlers: {e}")

    # Startup
    logger.info("=" * 60)
    logger.info(f"{APP_NAME} v{APP_VERSION} starting up...")

    try:
        services_status = await init_databases()
        log_startup_banner(settings, services_status)
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        logger.error("=" * 60)
        raise

    yield

    # Shutdown
    logger.info("=" * 60)
    log_shutdown_info()
    logger.info("Shutting down gracefully...")

    # Give in-flight requests time to complete (configurable timeout)
    shutdown_timeout = getattr(settings, "shutdown_timeout", 30)
    logger.info(
        f"Waiting up to {shutdown_timeout}s for in-flight requests to complete..."
    )

    # Note: Uvicorn handles request draining automatically when receiving SIGTERM
    # The timeout here is for our cleanup operations

    await close_databases()

    logger.info("Graceful shutdown complete")
    logger.info("=" * 60)


app = FastAPI(
    title=APP_NAME,
    description="Knowledge Management Platform API",
    version=APP_VERSION,
    lifespan=lifespan,
)


# =============================================================================
# SD-016: Standardized Exception Handlers
# =============================================================================


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors with standardized format (SD-016)."""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error.get("loc", []))
        errors.append(
            {
                "field": field,
                "message": error.get("msg", "Validation error"),
                "type": error.get("type", "value_error"),
            }
        )

    response = create_validation_error_response(
        message="Request validation failed",
        errors=errors,
        request_id=get_request_id(request),
        path=str(request.url.path),
    )

    logger.warning(
        f"Validation error on {request.method} {request.url.path}: "
        f"{len(errors)} error(s)"
    )

    return JSONResponse(status_code=422, content=response)


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """Handle Pydantic ValidationError (from manual validation) with standardized format."""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error.get("loc", []))
        errors.append(
            {
                "field": field,
                "message": error.get("msg", "Validation error"),
                "type": error.get("type", "value_error"),
            }
        )

    response = create_validation_error_response(
        message="Data validation failed",
        errors=errors,
        request_id=get_request_id(request),
        path=str(request.url.path),
    )

    return JSONResponse(status_code=422, content=response)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Handle HTTP exceptions with standardized format (SD-016)."""
    # Map status codes to error types
    error_type_map = {
        400: ErrorType.BAD_REQUEST,
        401: ErrorType.UNAUTHORIZED,
        403: ErrorType.FORBIDDEN,
        404: ErrorType.NOT_FOUND,
        409: ErrorType.CONFLICT,
        429: ErrorType.RATE_LIMITED,
        503: ErrorType.SERVICE_UNAVAILABLE,
    }

    error_type = error_type_map.get(exc.status_code, ErrorType.INTERNAL_ERROR)
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)

    response = create_error_response(
        error=error_type,
        message=message,
        status_code=exc.status_code,
        request_id=get_request_id(request),
        path=str(request.url.path),
    )

    return JSONResponse(status_code=exc.status_code, content=response)


@app.exception_handler(CircuitBreakerOpen)
async def circuit_breaker_exception_handler(
    request: Request, exc: CircuitBreakerOpen
) -> JSONResponse:
    """Handle circuit breaker open exceptions with standardized format (SD-006, SD-016)."""
    response = create_error_response(
        error=ErrorType.CIRCUIT_BREAKER_OPEN,
        message=str(exc),
        status_code=503,
        details={
            "circuit_name": exc.name,
            "retry_after_seconds": exc.time_remaining,
        },
        request_id=get_request_id(request),
        path=str(request.url.path),
    )

    logger.warning(
        f"Circuit breaker '{exc.name}' rejected request to {request.url.path}. "
        f"Retry in {exc.time_remaining:.1f}s"
    )

    return JSONResponse(
        status_code=503,
        content=response,
        headers={"Retry-After": str(int(exc.time_remaining + 1))},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions with standardized format (SD-016)."""
    # Log the full exception for debugging
    logger.exception(
        f"Unhandled exception on {request.method} {request.url.path}: "
        f"{type(exc).__name__}: {exc}"
    )

    # Don't expose internal error details to clients
    response = create_error_response(
        error=ErrorType.INTERNAL_ERROR,
        message="An unexpected error occurred. Please try again later.",
        status_code=500,
        request_id=get_request_id(request),
        path=str(request.url.path),
    )

    return JSONResponse(status_code=500, content=response)


# =============================================================================
# Middleware (order matters: last added = first executed on request)
# =============================================================================

# DEVOPS-P2-1: Security headers middleware (outermost - runs last on response)
# Adds X-Content-Type-Options, X-Frame-Options, CSP, HSTS, etc.
app.add_middleware(SecurityHeadersMiddleware)

# SEC-010: Add request size limit middleware BEFORE other middleware
# This prevents DoS via large payloads
app.add_middleware(RequestSizeLimitMiddleware)

# SEC-011: CORS with restricted methods and headers
# Previously allowed ["*"] for both, which was unnecessarily permissive
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    # SEC-011: Only allow methods that are actually used
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    # SEC-011: Only allow headers that are actually needed
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Request-ID",
        "Accept",
        "Accept-Language",
        "Accept-Encoding",
    ],
    # Expose headers that frontend may need to read
    expose_headers=["X-Request-ID"],
    # Cache preflight for 1 hour
    max_age=3600,
)

# SD-021: GZip compression for API responses
# Compresses responses larger than 1000 bytes to reduce bandwidth
# Added last so it runs first on response (innermost middleware on response path)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# =============================================================================
# Routers
# =============================================================================

app.include_router(agent.router, prefix="/api/agent", tags=["Agent Context"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(decisions.router, prefix="/api/decisions", tags=["Decisions"])
app.include_router(graph.router, prefix="/api/graph", tags=["Graph"])
app.include_router(capture.router, prefix="/api/capture", tags=["Capture"])
app.include_router(git.router, prefix="/api/git", tags=["Git"])
app.include_router(ingest.router, prefix="/api/ingest", tags=["Ingest"])
app.include_router(projects.router, prefix="/api/projects", tags=["Projects"])
app.include_router(search.router, prefix="/api/search", tags=["Search"])
app.include_router(entities.router, prefix="/api/entities", tags=["Entities"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(export.router, prefix="/api/export", tags=["Export"])
app.include_router(
    notifications.router,
    prefix="/api/notifications",
    tags=["Notifications"],
)


# =============================================================================
# Health & Status Endpoints
# =============================================================================


@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy"}


@app.get("/health/ready")
async def readiness_check():
    """
    Readiness probe - checks if the application can serve traffic.
    Returns 503 if any critical dependency is unhealthy.
    """
    postgres_ok = await check_postgres_connection()
    neo4j_ok = await check_neo4j_connection()
    redis_ok = await check_redis_connection()

    all_healthy = postgres_ok and neo4j_ok and redis_ok

    status = {
        "ready": all_healthy,
        "checks": {
            "postgres": "healthy" if postgres_ok else "unhealthy",
            "neo4j": "healthy" if neo4j_ok else "unhealthy",
            "redis": "healthy" if redis_ok else "unhealthy",
        },
    }

    if not all_healthy:
        return JSONResponse(status_code=503, content=status)

    return status


@app.get("/health/live")
async def liveness_check():
    """
    Liveness probe - checks if the application process is running.
    This should be lightweight and not check external dependencies.
    """
    return {"alive": True}


@app.get("/health/circuits")
async def circuit_breaker_status():
    """
    Get status of all circuit breakers (SD-006).
    Useful for monitoring and debugging resilience patterns.
    """
    stats = get_circuit_breaker_stats()
    return {
        "circuit_breakers": [
            {
                "name": s.name,
                "state": s.state,
                "failure_count": s.failure_count,
                "success_count": s.success_count,
                "total_failures": s.total_failures,
                "total_successes": s.total_successes,
                "total_rejections": s.total_rejections,
            }
            for s in stats
        ]
    }


@app.get("/")
async def root():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "docs": "/docs",
    }
