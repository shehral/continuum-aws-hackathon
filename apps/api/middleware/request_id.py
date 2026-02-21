"""Request ID middleware for request tracing.

Generates a unique request ID for each incoming request and:
- Stores it in request.state.request_id for access in route handlers
- Adds X-Request-ID header to responses
- Sets logging context for structured logging
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from utils.logging import clear_request_context, set_request_context


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that generates and propagates request IDs.

    If an incoming request has an X-Request-ID header, it will be used.
    Otherwise, a new UUID will be generated.

    The request ID is:
    1. Stored in request.state.request_id
    2. Set in the logging context for structured logs
    3. Returned in the X-Request-ID response header
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Get existing request ID from header or generate new one
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Store in request state for access in route handlers
        request.state.request_id = request_id

        # Set logging context
        set_request_context(request_id=request_id)

        try:
            # Process the request
            response = await call_next(request)

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response
        finally:
            # Clear logging context
            clear_request_context()
