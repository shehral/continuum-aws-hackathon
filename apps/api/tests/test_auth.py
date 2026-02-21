"""Tests for authentication router and JWT validation.

This test suite covers the authentication utilities in routers/auth.py,
including JWT token validation, user extraction, and authentication requirements.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from jose import jwt

from routers.auth import get_current_user_id, require_auth

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_settings():
    """Mock settings with test secret key."""
    settings = MagicMock()
    settings.secret_key = "test-secret-key-for-jwt-validation"
    settings.get_secret_key = lambda: "test-secret-key-for-jwt-validation"
    settings.algorithm = "HS256"
    return settings


def create_test_jwt(
    payload: dict,
    secret: str = "test-secret-key-for-jwt-validation",
    algorithm: str = "HS256",
) -> str:
    """Helper to create test JWTs.

    Args:
        payload: JWT claims to encode
        secret: Secret key for signing
        algorithm: Algorithm to use for signing

    Returns:
        Encoded JWT token string
    """
    return jwt.encode(payload, secret, algorithm=algorithm)


# ============================================================================
# get_current_user_id Tests
# ============================================================================


class TestGetCurrentUserId:
    """Tests for the get_current_user_id dependency."""

    @pytest.mark.asyncio
    async def test_no_authorization_header(self):
        """Should return 'anonymous' when no Authorization header is provided."""
        result = await get_current_user_id(authorization=None)
        assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_empty_authorization_header(self):
        """Should return 'anonymous' when Authorization header is empty string."""
        result = await get_current_user_id(authorization="")
        assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_invalid_format_no_bearer(self, mock_settings):
        """Should return 'anonymous' when header doesn't start with 'Bearer'."""
        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization="Basic sometoken")
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_invalid_format_only_bearer(self, mock_settings):
        """Should return 'anonymous' when header is just 'Bearer' without token."""
        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization="Bearer")
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_invalid_format_too_many_parts(self, mock_settings):
        """Should return 'anonymous' when header has too many parts."""
        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization="Bearer token extra")
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_valid_jwt_returns_user_id(self, mock_settings):
        """Should return user ID from valid JWT 'sub' claim."""
        payload = {
            "sub": "user-12345",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization=f"Bearer {token}")
            assert result == "user-12345"

    @pytest.mark.asyncio
    async def test_valid_jwt_case_insensitive_bearer(self, mock_settings):
        """Should accept 'bearer' in any case (Bearer, bearer, BEARER)."""
        payload = {
            "sub": "user-case-test",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            # Test lowercase
            result = await get_current_user_id(authorization=f"bearer {token}")
            assert result == "user-case-test"

            # Test uppercase
            result = await get_current_user_id(authorization=f"BEARER {token}")
            assert result == "user-case-test"

    @pytest.mark.asyncio
    async def test_expired_jwt(self, mock_settings):
        """Should return 'anonymous' for expired token."""
        payload = {
            "sub": "user-expired",
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc)
            - timedelta(hours=1),  # Expired 1 hour ago
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization=f"Bearer {token}")
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_invalid_signature(self, mock_settings):
        """Should return 'anonymous' for token signed with wrong secret."""
        payload = {
            "sub": "user-wrong-secret",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        # Sign with a different secret
        token = create_test_jwt(payload, secret="wrong-secret-key")

        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization=f"Bearer {token}")
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_missing_sub_claim(self, mock_settings):
        """Should return 'anonymous' if JWT lacks 'sub' claim."""
        payload = {
            "user_id": "user-no-sub",  # Wrong claim name
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        # Create token without 'sub' - the implementation requires 'sub'
        token = jwt.encode(
            payload,
            "test-secret-key-for-jwt-validation",
            algorithm="HS256",
        )

        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization=f"Bearer {token}")
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_malformed_jwt_token(self, mock_settings):
        """Should return 'anonymous' for malformed JWT token."""
        with patch("routers.auth.get_settings", return_value=mock_settings):
            # Not a valid JWT structure
            result = await get_current_user_id(authorization="Bearer not.a.valid.jwt")
            assert result == "anonymous"

            # Completely invalid token
            result = await get_current_user_id(authorization="Bearer garbage")
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_missing_secret_key_in_settings(self):
        """Should return 'anonymous' if SECRET_KEY is not configured."""
        mock_settings = MagicMock()
        mock_settings.secret_key = ""  # Empty secret key
        mock_settings.algorithm = "HS256"

        payload = {
            "sub": "user-no-secret",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization=f"Bearer {token}")
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_none_secret_key_in_settings(self):
        """Should return 'anonymous' if SECRET_KEY is None."""
        mock_settings = MagicMock()
        mock_settings.secret_key = None  # None secret key
        mock_settings.algorithm = "HS256"

        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization="Bearer sometoken")
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_numeric_sub_claim_rejected(self, mock_settings):
        """Should reject numeric 'sub' claim per JWT spec (must be string).

        Per RFC 7519, the 'sub' claim should be a StringOrURI.
        python-jose enforces this when require_sub=True.
        """
        payload = {
            "sub": 12345,  # Numeric user ID - invalid per JWT spec
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization=f"Bearer {token}")
            # Should be rejected because 'sub' must be a string
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_string_numeric_sub_claim(self, mock_settings):
        """Should accept numeric string in 'sub' claim."""
        payload = {
            "sub": "12345",  # String containing numeric value - valid
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization=f"Bearer {token}")
            assert result == "12345"
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_uuid_sub_claim(self, mock_settings):
        """Should handle UUID format in 'sub' claim."""
        user_uuid = "550e8400-e29b-41d4-a716-446655440000"
        payload = {
            "sub": user_uuid,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization=f"Bearer {token}")
            assert result == user_uuid


# ============================================================================
# require_auth Tests
# ============================================================================


class TestRequireAuth:
    """Tests for the require_auth dependency."""

    @pytest.mark.asyncio
    async def test_raises_401_when_not_authenticated(self):
        """Should raise 401 HTTPException when no valid authentication."""
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(authorization=None)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Authentication required"
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}

    @pytest.mark.asyncio
    async def test_raises_401_for_invalid_token(self, mock_settings):
        """Should raise 401 HTTPException for invalid token."""
        with patch("routers.auth.get_settings", return_value=mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                await require_auth(authorization="Bearer invalid-token")

            assert exc_info.value.status_code == 401
            assert exc_info.value.detail == "Authentication required"

    @pytest.mark.asyncio
    async def test_raises_401_for_expired_token(self, mock_settings):
        """Should raise 401 HTTPException for expired token."""
        payload = {
            "sub": "user-expired",
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                await require_auth(authorization=f"Bearer {token}")

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_returns_user_id_when_authenticated(self, mock_settings):
        """Should return user_id when valid authentication is provided."""
        payload = {
            "sub": "authenticated-user-123",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await require_auth(authorization=f"Bearer {token}")
            assert result == "authenticated-user-123"

    @pytest.mark.asyncio
    async def test_returns_user_id_string_type(self, mock_settings):
        """Should always return user_id as string."""
        payload = {
            "sub": "99999",  # String ID (JWT spec requires sub to be string)
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await require_auth(authorization=f"Bearer {token}")
            assert result == "99999"
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_raises_401_for_numeric_sub(self, mock_settings):
        """Should raise 401 when 'sub' is numeric (invalid per JWT spec)."""
        payload = {
            "sub": 99999,  # Numeric - invalid per JWT spec
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                await require_auth(authorization=f"Bearer {token}")

            assert exc_info.value.status_code == 401


# ============================================================================
# Edge Cases and Security Tests
# ============================================================================


class TestSecurityEdgeCases:
    """Tests for security edge cases and attack vectors."""

    @pytest.mark.asyncio
    async def test_token_with_none_algorithm_attack(self, mock_settings):
        """Should reject tokens that try to use 'none' algorithm attack."""
        # The 'none' algorithm attack tries to bypass signature verification
        # This should be rejected because we explicitly set algorithms=[HS256]
        payload = {
            "sub": "attacker",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        # Create a token with 'none' algorithm (unsigned)
        header = {"alg": "none", "typ": "JWT"}
        import base64
        import json

        header_b64 = (
            base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
        )
        payload_b64 = (
            base64.urlsafe_b64encode(json.dumps(payload, default=str).encode())
            .rstrip(b"=")
            .decode()
        )
        fake_token = f"{header_b64}.{payload_b64}."

        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization=f"Bearer {fake_token}")
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_token_with_correct_algorithm(self, mock_settings):
        """Should accept tokens signed with correct algorithm."""
        payload = {
            "sub": "user-hs256",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization=f"Bearer {token}")
            # Should work with correct algorithm
            assert result == "user-hs256"

    @pytest.mark.asyncio
    async def test_token_with_very_long_sub_claim(self, mock_settings):
        """Should handle tokens with very long 'sub' claim."""
        long_user_id = "user-" + "x" * 10000  # 10K character user ID
        payload = {
            "sub": long_user_id,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization=f"Bearer {token}")
            assert result == long_user_id

    @pytest.mark.asyncio
    async def test_token_with_special_characters_in_sub(self, mock_settings):
        """Should handle tokens with special characters in 'sub' claim."""
        special_user_id = "user@example.com"
        payload = {
            "sub": special_user_id,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization=f"Bearer {token}")
            assert result == special_user_id

    @pytest.mark.asyncio
    async def test_token_with_unicode_in_sub(self, mock_settings):
        """Should handle tokens with unicode characters in 'sub' claim."""
        unicode_user_id = "user-\u00e9\u00e8\u00ea"  # accented characters
        payload = {
            "sub": unicode_user_id,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization=f"Bearer {token}")
            assert result == unicode_user_id

    @pytest.mark.asyncio
    async def test_whitespace_in_header_tolerant(self, mock_settings):
        """Implementation uses split() which handles multiple spaces.

        Python's str.split() without arguments splits on any whitespace
        and collapses multiple spaces, so 'Bearer  token' is valid.
        """
        payload = {
            "sub": "user-whitespace",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            # Multiple spaces between Bearer and token - works due to split()
            result = await get_current_user_id(authorization=f"Bearer  {token}")
            assert result == "user-whitespace"

    @pytest.mark.asyncio
    async def test_token_with_empty_sub_claim(self, mock_settings):
        """Should return 'anonymous' when 'sub' is empty string."""
        payload = {
            "sub": "",  # Empty string
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization=f"Bearer {token}")
            # Empty sub should be treated as invalid/anonymous
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_only_token_no_bearer_prefix(self, mock_settings):
        """Should reject authorization that is just the token without Bearer prefix."""
        payload = {
            "sub": "user-no-bearer",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = create_test_jwt(payload)

        with patch("routers.auth.get_settings", return_value=mock_settings):
            # Just the token, no "Bearer " prefix
            result = await get_current_user_id(authorization=token)
            assert result == "anonymous"


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
