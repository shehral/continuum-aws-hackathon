"""Security headers middleware for production hardening (DEVOPS-P2-1).

Adds essential security headers to all responses to protect against common
web vulnerabilities like XSS, clickjacking, and MIME sniffing attacks.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses.

    Headers added:
    - X-Content-Type-Options: nosniff (prevent MIME sniffing)
    - X-Frame-Options: DENY (prevent clickjacking)
    - X-XSS-Protection: 0 (disable legacy XSS filter, rely on CSP)
    - Referrer-Policy: strict-origin-when-cross-origin
    - Strict-Transport-Security: max-age=31536000 (HTTPS only, 1 year)
    - Content-Security-Policy: Basic restrictive policy
    - Permissions-Policy: Restrict browser features

    Note: Strict-Transport-Security (HSTS) is only added when the request
    is over HTTPS to avoid issues in development.
    """

    # Default CSP policy - restrictive but functional for API
    DEFAULT_CSP = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    # Permissions policy to restrict browser features
    DEFAULT_PERMISSIONS_POLICY = (
        "accelerometer=(), "
        "camera=(), "
        "geolocation=(), "
        "gyroscope=(), "
        "magnetometer=(), "
        "microphone=(), "
        "payment=(), "
        "usb=()"
    )

    def __init__(self, app, enable_hsts: bool = True, csp: str = None):
        """Initialize security headers middleware.

        Args:
            app: The ASGI application
            enable_hsts: Whether to add HSTS header (default: True)
            csp: Custom Content-Security-Policy header value
        """
        super().__init__(app)
        self.enable_hsts = enable_hsts
        self.csp = csp or self.DEFAULT_CSP

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # X-Content-Type-Options: Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # X-Frame-Options: Prevent clickjacking
        # DENY is more secure than SAMEORIGIN for APIs
        response.headers["X-Frame-Options"] = "DENY"

        # X-XSS-Protection: Disable legacy XSS filter
        # Modern browsers use CSP instead, and the filter can introduce vulnerabilities
        response.headers["X-XSS-Protection"] = "0"

        # Referrer-Policy: Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content-Security-Policy: Restrict resource loading
        # For APIs, this is mainly useful for error pages
        response.headers["Content-Security-Policy"] = self.csp

        # Permissions-Policy: Restrict browser features
        response.headers["Permissions-Policy"] = self.DEFAULT_PERMISSIONS_POLICY

        # Strict-Transport-Security: Force HTTPS
        # Only add if:
        # 1. HSTS is enabled
        # 2. Request is over HTTPS (or behind a proxy with X-Forwarded-Proto)
        if self.enable_hsts:
            is_https = (
                request.url.scheme == "https"
                or request.headers.get("X-Forwarded-Proto") == "https"
            )
            if is_https:
                # max-age=31536000 = 1 year
                # includeSubDomains = apply to all subdomains
                # preload = allow inclusion in browser HSTS preload lists
                response.headers["Strict-Transport-Security"] = (
                    "max-age=31536000; includeSubDomains; preload"
                )

        return response


class TrustedHostMiddleware:
    """Middleware to validate the Host header against allowed hosts.

    This prevents host header injection attacks by rejecting requests
    with unexpected Host headers.
    """

    def __init__(self, app, allowed_hosts: list[str] = None):
        """Initialize trusted host middleware.

        Args:
            app: The ASGI application
            allowed_hosts: List of allowed host names (default: from settings)
        """
        self.app = app
        settings = get_settings()

        # Get allowed hosts from settings or use defaults
        if allowed_hosts is not None:
            self.allowed_hosts = set(allowed_hosts)
        else:
            # Default to localhost for development
            self.allowed_hosts = {
                "localhost",
                "127.0.0.1",
                "0.0.0.0",
            }
            # Add any configured allowed hosts from CORS origins
            for origin in settings.cors_origins:
                # Extract host from origin URL
                if "://" in origin:
                    host = origin.split("://")[1].split(":")[0].split("/")[0]
                    self.allowed_hosts.add(host)

        # Wildcard means allow all hosts (useful for development)
        self.allow_all = "*" in self.allowed_hosts

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        if self.allow_all:
            await self.app(scope, receive, send)
            return

        # Get host header
        headers = dict(scope.get("headers", []))
        host_header = headers.get(b"host", b"").decode("latin-1")

        # Extract host without port
        host = host_header.split(":")[0].lower()

        if host not in self.allowed_hosts:
            logger.warning(
                f"Rejected request with untrusted host header: {host_header}",
                extra={"host": host_header, "allowed": list(self.allowed_hosts)},
            )
            # Return 400 Bad Request
            response = {
                "type": "http.response.start",
                "status": 400,
                "headers": [(b"content-type", b"application/json")],
            }
            await send(response)

            body = b'{"detail": "Invalid host header"}'
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
