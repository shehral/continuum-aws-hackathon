"""Request size limit middleware for DoS protection (SEC-010)."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from utils.logging import get_logger

logger = get_logger(__name__)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to limit request body size for DoS protection.

    SEC-010: Prevents denial of service via large request payloads.
    """

    # Default: 100KB for most endpoints
    DEFAULT_MAX_SIZE = 100 * 1024  # 100KB

    # Larger limit for specific paths that may need it
    LARGE_PAYLOAD_PATHS = {
        "/api/ingest": 1 * 1024 * 1024,  # 1MB for file ingestion
    }

    def __init__(self, app, max_size: int = None):
        super().__init__(app)
        self.default_max_size = max_size or self.DEFAULT_MAX_SIZE

    async def dispatch(self, request: Request, call_next):
        # Determine max size based on path
        max_size = self.default_max_size
        for path_prefix, size_limit in self.LARGE_PAYLOAD_PATHS.items():
            if request.url.path.startswith(path_prefix):
                max_size = size_limit
                break

        # Check Content-Length header
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                length = int(content_length)
                if length > max_size:
                    logger.warning(
                        f"Request body too large: {length} bytes (max: {max_size})",
                        extra={
                            "path": request.url.path,
                            "content_length": length,
                            "max_size": max_size,
                        },
                    )
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": f"Request body too large. Maximum size is {max_size // 1024}KB."
                        },
                    )
            except ValueError:
                # Invalid Content-Length header, let it pass and fail later
                pass

        return await call_next(request)
