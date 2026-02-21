"""Logging middleware for request/response logging with PII sanitization (SEC-015).

Logs incoming requests and outgoing responses with timing information.
Integrates with the structured logging system for request context.
SEC-015: Sanitizes sensitive data before logging.
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from utils.logging import get_logger, set_request_context
from utils.sanitize import mask_ip, sanitize_user_id

logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs requests and responses.

    Logs:
    - Incoming request: method, path, masked client IP
    - Outgoing response: status code, duration
    - Sets user_id in logging context from auth header

    SEC-015: Sanitizes PII (IP addresses, user IDs) before logging.
    """

    # Paths to exclude from detailed logging
    EXCLUDE_PATHS = {"/health", "/health/ready", "/health/live", "/metrics"}

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip logging for excluded paths (reduces noise)
        if path in self.EXCLUDE_PATHS:
            return await call_next(request)

        # Extract user info if available (from JWT claim stored by auth middleware)
        user_id = None
        sanitized_user_id = "anonymous"
        if hasattr(request.state, "user_id"):
            user_id = request.state.user_id
            # SEC-015: Use hashed user_id in logs
            sanitized_user_id = sanitize_user_id(user_id)
            set_request_context(user_id=sanitized_user_id)

        method = request.method
        # SEC-015: Mask client IP for privacy
        raw_client_ip = request.client.host if request.client else "unknown"
        masked_client_ip = (
            mask_ip(raw_client_ip) if raw_client_ip != "unknown" else "unknown"
        )

        # Log incoming request
        logger.info(
            f"Request: {method} {path}",
            extra={
                "event": "request_start",
                "method": method,
                "path": path,
                "client_ip": masked_client_ip,  # SEC-015: Masked IP
                # SEC-015: Don't log full user-agent (can contain PII)
                "user_agent_length": len(request.headers.get("user-agent", "")),
            },
        )

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            duration = time.perf_counter() - start_time

            # Log response
            log_level = "warning" if response.status_code >= 400 else "info"
            getattr(logger, log_level)(
                f"Response: {method} {path} - {response.status_code} ({duration:.3f}s)",
                extra={
                    "event": "request_complete",
                    "method": method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_seconds": duration,
                },
            )

            return response

        except Exception as e:
            duration = time.perf_counter() - start_time

            # Log exception (SEC-015: Don't include exception message as it may contain PII)
            logger.error(
                f"Request failed: {method} {path} - {type(e).__name__}",
                extra={
                    "event": "request_error",
                    "method": method,
                    "path": path,
                    "duration_seconds": duration,
                    "error_type": type(e).__name__,
                    # SEC-015: Log exception class only, not message (may contain PII)
                },
                exc_info=True,  # Full traceback will be in error logs, not JSON
            )
            raise
