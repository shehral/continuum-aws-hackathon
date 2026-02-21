"""Standardized error response schema for consistent API error handling (SD-016).

This module provides a consistent error response format across all API endpoints,
making it easier for frontend clients to handle errors uniformly.

Usage:
    from models.errors import ErrorResponse, create_error_response

    # In exception handlers:
    return create_error_response(
        error="ValidationError",
        message="Invalid input data",
        details={"field": "email", "issue": "Invalid format"},
        request_id=request.state.request_id,
    )

Error response format:
{
    "error": "ValidationError",
    "message": "The email field has an invalid format",
    "details": {"field": "email", "constraint": "email_format"},
    "request_id": "abc-123-def-456",
    "timestamp": "2026-01-29T12:00:00Z",
    "path": "/api/users/create"
}
"""

from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response schema for all API endpoints.

    Attributes:
        error: Error type/code (e.g., "ValidationError", "NotFound", "ServiceUnavailable")
        message: Human-readable error message suitable for display to users
        details: Optional additional context about the error (validation errors, etc.)
        request_id: Optional request correlation ID for tracing
        timestamp: When the error occurred (ISO 8601 format)
        path: Optional request path that caused the error
    """

    error: str = Field(
        ...,
        description="Error type/code (e.g., 'ValidationError', 'NotFound')",
        examples=["ValidationError", "NotFound", "ServiceUnavailable"],
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
        examples=["The requested resource was not found"],
    )
    details: Optional[dict[str, Any]] = Field(
        default=None,
        description="Additional error context (validation errors, etc.)",
        examples=[{"field": "email", "issue": "Invalid format"}],
    )
    request_id: Optional[str] = Field(
        default=None,
        description="Request correlation ID for tracing",
        examples=["abc123-def456-ghi789"],
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="When the error occurred (ISO 8601)",
    )
    path: Optional[str] = Field(
        default=None,
        description="Request path that caused the error",
        examples=["/api/decisions/123"],
    )


class ValidationErrorDetail(BaseModel):
    """Detail for a single validation error."""

    field: str = Field(..., description="Field that failed validation")
    message: str = Field(..., description="Validation error message")
    type: str = Field(..., description="Type of validation error")


class ValidationErrorResponse(ErrorResponse):
    """Extended error response for validation errors with field details."""

    error: str = "ValidationError"
    validation_errors: list[ValidationErrorDetail] = Field(
        default_factory=list,
        description="List of field-level validation errors",
    )


# Common error types as constants
class ErrorType:
    """Standard error type codes."""

    VALIDATION_ERROR = "ValidationError"
    NOT_FOUND = "NotFound"
    UNAUTHORIZED = "Unauthorized"
    FORBIDDEN = "Forbidden"
    CONFLICT = "Conflict"
    RATE_LIMITED = "RateLimited"
    SERVICE_UNAVAILABLE = "ServiceUnavailable"
    INTERNAL_ERROR = "InternalError"
    BAD_REQUEST = "BadRequest"
    CIRCUIT_BREAKER_OPEN = "CircuitBreakerOpen"
    DATABASE_ERROR = "DatabaseError"
    EXTERNAL_SERVICE_ERROR = "ExternalServiceError"


def create_error_response(
    error: str,
    message: str,
    status_code: int = 500,
    details: Optional[dict[str, Any]] = None,
    request_id: Optional[str] = None,
    path: Optional[str] = None,
) -> dict[str, Any]:
    """Create a standardized error response dictionary.

    Args:
        error: Error type/code
        message: Human-readable error message
        status_code: HTTP status code (not included in response, for logging)
        details: Optional additional context
        request_id: Optional request correlation ID
        path: Optional request path

    Returns:
        Dictionary suitable for JSONResponse content
    """
    response = ErrorResponse(
        error=error,
        message=message,
        details=details,
        request_id=request_id,
        path=path,
    )
    return response.model_dump(exclude_none=True)


def create_validation_error_response(
    message: str,
    errors: list[dict[str, str]],
    request_id: Optional[str] = None,
    path: Optional[str] = None,
) -> dict[str, Any]:
    """Create a validation error response with field-level details.

    Args:
        message: Overall error message
        errors: List of {"field": str, "message": str, "type": str} dicts
        request_id: Optional request correlation ID
        path: Optional request path

    Returns:
        Dictionary suitable for JSONResponse content
    """
    validation_errors = [
        ValidationErrorDetail(
            field=e.get("field", "unknown"),
            message=e.get("message", "Validation failed"),
            type=e.get("type", "value_error"),
        )
        for e in errors
    ]

    response = ValidationErrorResponse(
        error=ErrorType.VALIDATION_ERROR,
        message=message,
        validation_errors=validation_errors,
        request_id=request_id,
        path=path,
    )
    return response.model_dump(exclude_none=True)
