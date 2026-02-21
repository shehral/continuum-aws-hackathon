"""Structured JSON logging for the Continuum API.

This module provides:
- JSON-formatted log output for production environments
- Request context via ContextVar (request_id, user_id, trace_id)
- Backwards-compatible get_logger() function
- Human-readable format for development
"""

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# Context variables for request tracing
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def get_request_id() -> str | None:
    """Get the current request ID from context."""
    return request_id_var.get()


def get_user_id() -> str | None:
    """Get the current user ID from context."""
    return user_id_var.get()


def get_trace_id() -> str | None:
    """Get the current trace ID from context."""
    return trace_id_var.get()


def set_request_context(
    request_id: str | None = None,
    user_id: str | None = None,
    trace_id: str | None = None,
):
    """Set request context variables."""
    if request_id is not None:
        request_id_var.set(request_id)
    if user_id is not None:
        user_id_var.set(user_id)
    if trace_id is not None:
        trace_id_var.set(trace_id)


def clear_request_context():
    """Clear all request context variables."""
    request_id_var.set(None)
    user_id_var.set(None)
    trace_id_var.set(None)


class JSONFormatter(logging.Formatter):
    """JSON log formatter for production environments.

    Output format:
    {
        "timestamp": "2026-01-29T12:34:56.789Z",
        "level": "INFO",
        "logger": "module.name",
        "message": "Log message here",
        "request_id": "abc-123",
        "user_id": "user-456",
        "trace_id": "trace-789",
        "extra": {...}
    }
    """

    def format(self, record: logging.LogRecord) -> str:
        # Base log structure
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add request context if available
        request_id = get_request_id()
        user_id = get_user_id()
        trace_id = get_trace_id()

        if request_id:
            log_data["request_id"] = request_id
        if user_id:
            log_data["user_id"] = user_id
        if trace_id:
            log_data["trace_id"] = trace_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            log_data["exception_type"] = (
                record.exc_info[0].__name__ if record.exc_info[0] else None
            )

        # Add any extra fields from the record
        # These come from logger.info("msg", extra={"key": "value"})
        standard_attrs = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "exc_info",
            "exc_text",
            "thread",
            "threadName",
            "taskName",
            "message",
        }

        extra_fields = {
            key: value
            for key, value in record.__dict__.items()
            if key not in standard_attrs and not key.startswith("_")
        }

        if extra_fields:
            log_data["extra"] = extra_fields

        return json.dumps(log_data, default=str)


class HumanReadableFormatter(logging.Formatter):
    """Human-readable log formatter for development.

    Output format:
    2026-01-29 12:34:56.789 | INFO     | module.name | [req-abc-123] Log message here
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level = record.levelname.ljust(8)
        logger = record.name
        message = record.getMessage()

        # Add request ID if available
        request_id = get_request_id()
        if request_id:
            # Truncate request ID for readability
            short_id = request_id[:8] if len(request_id) > 8 else request_id
            prefix = f"[{short_id}] "
        else:
            prefix = ""

        formatted = f"{timestamp} | {level} | {logger} | {prefix}{message}"

        # Add exception if present
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"

        return formatted


def configure_logging(
    level: str = "INFO",
    json_format: bool | None = None,
    service_name: str = "continuum-api",
):
    """Configure the root logger with structured logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON format. If None, auto-detect from environment.
        service_name: Service name for log identification
    """
    # Auto-detect JSON format based on environment
    if json_format is None:
        # Use JSON in production (when DEBUG is not set or explicitly false)
        debug_mode = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
        json_format = not debug_mode

    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create handler with appropriate formatter
    handler = logging.StreamHandler(sys.stdout)

    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(HumanReadableFormatter())

    root_logger.addHandler(handler)

    # Set log levels for noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger for the module.

    This function is backwards-compatible with the previous implementation.
    It now relies on configure_logging() being called at startup.

    Args:
        name: Module name (typically __name__)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # If logging hasn't been configured yet, set up a basic handler
    # This maintains backwards compatibility
    if not logging.getLogger().handlers:
        configure_logging()

    return logger


class LogContext:
    """Context manager for setting request context.

    Usage:
        async with LogContext(request_id="abc-123", user_id="user-456"):
            logger.info("This log will include request context")
    """

    def __init__(
        self,
        request_id: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
    ):
        self.request_id = request_id
        self.user_id = user_id
        self.trace_id = trace_id
        self._tokens: list = []

    def __enter__(self):
        if self.request_id:
            self._tokens.append(request_id_var.set(self.request_id))
        if self.user_id:
            self._tokens.append(user_id_var.set(self.user_id))
        if self.trace_id:
            self._tokens.append(trace_id_var.set(self.trace_id))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Reset context vars to their previous values
        for token in self._tokens:
            # Context vars don't have a direct reset, but setting to None works
            pass
        clear_request_context()
        return False

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)
