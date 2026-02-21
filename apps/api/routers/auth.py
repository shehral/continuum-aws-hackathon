"""Authentication utilities for FastAPI routes (SEC-007 compliant)."""

from typing import Optional

from fastapi import Header, HTTPException
from jose import JWTError, jwt

from config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


async def get_current_user_id(
    authorization: Optional[str] = Header(None),
) -> str:
    """Extract and validate user ID from Authorization header.

    Validates JWT tokens signed by NextAuth using the shared secret.
    Returns "anonymous" if no valid authentication is provided.

    SEC-007: Secret key is accessed via SecretStr.get_secret_value() to prevent
    accidental exposure in logs or error messages.

    Args:
        authorization: Authorization header value (Bearer <token>)

    Returns:
        User ID string from JWT 'sub' claim, or "anonymous" if no auth provided
    """
    if not authorization:
        return "anonymous"

    settings = get_settings()

    # SEC-007: Use getter method to safely retrieve secret key
    secret_key = settings.get_secret_key()

    # Require secret_key to be configured for JWT validation
    if not secret_key:
        logger.error("SECRET_KEY not configured - cannot validate JWT tokens")
        return "anonymous"

    try:
        # Expected format: "Bearer <jwt_token>"
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.warning("Invalid authorization header format")
            return "anonymous"

        token = parts[1]

        # Validate and decode the JWT token
        try:
            payload = jwt.decode(
                token,
                secret_key,
                algorithms=[settings.algorithm],
                options={
                    "require_sub": True,  # Require 'sub' claim
                    "verify_exp": True,  # Verify expiration
                    "verify_iat": True,  # Verify issued-at
                },
            )
        except JWTError:
            # SEC-007: Don't log the actual token or error details that might expose secrets
            logger.warning("JWT validation failed")
            return "anonymous"

        # Extract user ID from the 'sub' claim
        user_id = payload.get("sub")
        if not user_id:
            logger.warning("JWT token missing 'sub' claim")
            return "anonymous"

        return str(user_id)

    except Exception:
        # SEC-007: Don't log exception details that might contain token data
        logger.warning("Auth extraction failed")
        return "anonymous"


async def require_auth(
    authorization: Optional[str] = Header(None),
) -> str:
    """Require authentication - raises 401 if not authenticated.

    Use this dependency when authentication is required.
    """
    user_id = await get_current_user_id(authorization)
    if user_id == "anonymous":
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id
