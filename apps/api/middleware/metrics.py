"""Metrics middleware for Prometheus instrumentation.

Captures request metrics including:
- Request count by method, endpoint, and status code
- Request duration histogram by method and endpoint
"""

import re
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from utils.metrics import REQUEST_COUNT, REQUEST_DURATION


def normalize_path(path: str) -> str:
    """Normalize path to reduce cardinality.

    Replaces dynamic path segments (UUIDs, IDs) with placeholders
    to prevent metric cardinality explosion.
    """
    # Replace UUIDs with placeholder
    path = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "{id}",
        path,
        flags=re.IGNORECASE,
    )

    # Replace numeric IDs with placeholder
    path = re.sub(r"/\d+(?=/|$)", "/{id}", path)

    return path


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware that collects HTTP request metrics.

    Metrics collected:
    - continuum_http_requests_total: Counter with method, endpoint, status_code labels
    - continuum_http_request_duration_seconds: Histogram with method, endpoint labels
    """

    # Paths to exclude from metrics (health checks, metrics endpoint itself)
    EXCLUDE_PATHS = {"/health", "/health/ready", "/health/live", "/metrics", "/"}

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip metrics for excluded paths
        if path in self.EXCLUDE_PATHS:
            return await call_next(request)

        method = request.method
        normalized_path = normalize_path(path)

        # Record start time
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            # Record 500 for unhandled exceptions
            status_code = 500
            raise
        finally:
            # Record duration
            duration = time.perf_counter() - start_time

            # Update metrics
            REQUEST_COUNT.labels(
                method=method, endpoint=normalized_path, status_code=str(status_code)
            ).inc()

            REQUEST_DURATION.labels(method=method, endpoint=normalized_path).observe(
                duration
            )

        return response
