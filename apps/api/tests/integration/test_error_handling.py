"""Tests for error handling across the API.

This test suite verifies consistent error handling across all API endpoints:
- 400 Bad Request for invalid input
- 401 Unauthorized for missing/invalid auth
- 403 Forbidden for unauthorized access
- 404 Not Found for missing resources
- 422 Validation Error for schema violations
- 500 Internal Server Error formatting
- 503 Service Unavailable for database issues

All error responses should follow a consistent schema with 'detail' field.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from neo4j.exceptions import ClientError, DatabaseError, DriverError

from routers.auth import get_current_user_id, require_auth

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_neo4j_session():
    """Create a mock Neo4j async session."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.get_secret_key.return_value = "test-secret-key"
    settings.algorithm = "HS256"
    return settings


# ============================================================================
# 400 Bad Request Tests
# ============================================================================


class TestBadRequest:
    """Tests for 400 Bad Request responses."""

    @pytest.mark.asyncio
    async def test_invalid_decision_id_format(self, mock_neo4j_session):
        """Should return 404 for malformed decision IDs that don't match."""
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.decisions import get_decision

            with pytest.raises(HTTPException) as exc_info:
                await get_decision("invalid-not-uuid", user_id="test-user")
            # Returns 404 because no record found
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_entity_delete_with_relationships(self, mock_neo4j_session):
        """Should return 400 when deleting entity with relationships."""
        # Mock entity exists and is accessible
        mock_entity_result = AsyncMock()
        mock_entity_result.single = AsyncMock(return_value={"e": {"id": "test-id"}})

        # Mock no other users have access
        mock_other_users_result = AsyncMock()
        mock_other_users_result.single = AsyncMock(return_value={"other_user_count": 0})

        # Mock entity has relationships
        mock_rel_result = AsyncMock()
        mock_rel_result.single = AsyncMock(return_value={"rel_count": 5})

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_entity_result
            elif call_count[0] == 2:
                return mock_other_users_result
            else:
                return mock_rel_result

        mock_neo4j_session.run = mock_run

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.entities import delete_entity

            with pytest.raises(HTTPException) as exc_info:
                await delete_entity("test-entity-id", force=False, user_id="test-user")

            assert exc_info.value.status_code == 400
            assert "relationships" in exc_info.value.detail.lower()


# ============================================================================
# 401 Unauthorized Tests
# ============================================================================


class TestUnauthorized:
    """Tests for 401 Unauthorized responses."""

    @pytest.mark.asyncio
    async def test_missing_auth_header(self):
        """Should return 'anonymous' when no auth header provided."""
        result = await get_current_user_id(authorization=None)
        assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_require_auth_missing_header(self):
        """Should raise 401 when auth is required but missing."""
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(authorization=None)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Authentication required"
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}

    @pytest.mark.asyncio
    async def test_invalid_bearer_format(self, mock_settings):
        """Should return 'anonymous' for invalid bearer format."""
        with patch("routers.auth.get_settings", return_value=mock_settings):
            result = await get_current_user_id(authorization="InvalidFormat token")
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_require_auth_invalid_token(self, mock_settings):
        """Should raise 401 for invalid token when auth required."""
        with patch("routers.auth.get_settings", return_value=mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                await require_auth(authorization="Bearer invalid-token-here")

            assert exc_info.value.status_code == 401


# ============================================================================
# 403 Forbidden Tests
# ============================================================================


class TestForbidden:
    """Tests for 403 Forbidden responses."""

    @pytest.mark.asyncio
    async def test_entity_delete_shared_with_other_users(self, mock_neo4j_session):
        """Should return 403 when deleting entity shared with other users."""
        # Mock entity exists and is accessible
        mock_entity_result = AsyncMock()
        mock_entity_result.single = AsyncMock(
            return_value={"e": {"id": "shared-entity"}}
        )

        # Mock other users have access
        mock_other_users_result = AsyncMock()
        mock_other_users_result.single = AsyncMock(return_value={"other_user_count": 3})

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_entity_result
            else:
                return mock_other_users_result

        mock_neo4j_session.run = mock_run

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.entities import delete_entity

            with pytest.raises(HTTPException) as exc_info:
                await delete_entity("shared-entity", force=True, user_id="user-a")

            assert exc_info.value.status_code == 403
            assert "other users" in exc_info.value.detail.lower()


# ============================================================================
# 404 Not Found Tests
# ============================================================================


class TestNotFound:
    """Tests for 404 Not Found responses."""

    @pytest.mark.asyncio
    async def test_decision_not_found(self, mock_neo4j_session):
        """Should return 404 for non-existent decision."""
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.decisions import get_decision

            with pytest.raises(HTTPException) as exc_info:
                await get_decision(str(uuid4()), user_id="test-user")

            assert exc_info.value.status_code == 404
            assert exc_info.value.detail == "Decision not found"

    @pytest.mark.asyncio
    async def test_entity_not_found(self, mock_neo4j_session):
        """Should return 404 for non-existent entity."""
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.entities import get_entity

            with pytest.raises(HTTPException) as exc_info:
                await get_entity(str(uuid4()), user_id="test-user")

            assert exc_info.value.status_code == 404
            assert exc_info.value.detail == "Entity not found"

    @pytest.mark.asyncio
    async def test_delete_nonexistent_decision(self, mock_neo4j_session):
        """Should return 404 when deleting non-existent decision."""
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.decisions import delete_decision

            with pytest.raises(HTTPException) as exc_info:
                await delete_decision(str(uuid4()), user_id="test-user")

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_link_entity_nonexistent_decision(self, mock_neo4j_session):
        """Should return 404 when linking to non-existent decision."""
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value={"exists": False})
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from models.schemas import LinkEntityRequest
            from routers.entities import link_entity

            request = LinkEntityRequest(
                decision_id=str(uuid4()),
                entity_id=str(uuid4()),
                relationship="INVOLVES",
            )

            with pytest.raises(HTTPException) as exc_info:
                await link_entity(request, user_id="test-user")

            assert exc_info.value.status_code == 404


# ============================================================================
# 422 Validation Error Tests
# ============================================================================


class TestValidationError:
    """Tests for 422 Validation Error responses."""

    def test_invalid_uuid_pattern_in_request(self):
        """Should reject invalid UUID patterns."""
        from pydantic import ValidationError

        from models.schemas import LinkEntityRequest

        # Invalid UUID format
        with pytest.raises(ValidationError) as exc_info:
            LinkEntityRequest(
                decision_id="not-a-valid-uuid!@#$",
                entity_id=str(uuid4()),
                relationship="INVOLVES",
            )

        # Check that validation error mentions the field
        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any("decision_id" in str(e) for e in errors)

    def test_invalid_relationship_type(self):
        """Should reject invalid relationship types."""
        from pydantic import ValidationError

        from models.schemas import LinkEntityRequest

        with pytest.raises(ValidationError) as exc_info:
            LinkEntityRequest(
                decision_id=str(uuid4()),
                entity_id=str(uuid4()),
                relationship="INVALID_RELATIONSHIP_TYPE",
            )

        errors = exc_info.value.errors()
        assert len(errors) > 0

    def test_missing_required_fields(self):
        """Should require mandatory fields."""
        from pydantic import ValidationError

        from models.schemas import DecisionCreate

        with pytest.raises(ValidationError):
            DecisionCreate()  # Missing all required fields


# ============================================================================
# 500 Internal Server Error Tests
# ============================================================================


class TestInternalServerError:
    """Tests for 500 Internal Server Error responses."""

    @pytest.mark.asyncio
    async def test_database_query_error(self, mock_neo4j_session):
        """Should return 500 for database query errors."""
        mock_neo4j_session.run = AsyncMock(side_effect=DatabaseError("Query failed"))

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.decisions import get_decisions

            with pytest.raises(HTTPException) as exc_info:
                await get_decisions(limit=50, offset=0, user_id="test-user")

            assert exc_info.value.status_code == 500
            assert "failed to fetch" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_client_error_returns_500(self, mock_neo4j_session):
        """Should return 500 for Neo4j client errors."""
        mock_neo4j_session.run = AsyncMock(
            side_effect=ClientError("Invalid Cypher syntax")
        )

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.entities import get_all_entities

            with pytest.raises(HTTPException) as exc_info:
                await get_all_entities(user_id="test-user")

            assert exc_info.value.status_code == 500


# ============================================================================
# 503 Service Unavailable Tests
# ============================================================================


class TestServiceUnavailable:
    """Tests for 503 Service Unavailable responses."""

    @pytest.mark.asyncio
    async def test_database_connection_failure(self, mock_neo4j_session):
        """Should return 503 for database connection failures."""
        mock_neo4j_session.run = AsyncMock(
            side_effect=DriverError("Connection refused")
        )

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.decisions import get_decisions

            with pytest.raises(HTTPException) as exc_info:
                await get_decisions(limit=50, offset=0, user_id="test-user")

            assert exc_info.value.status_code == 503
            assert "database unavailable" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_entity_fetch_connection_failure(self, mock_neo4j_session):
        """Should return 503 when database unavailable for entities."""
        mock_neo4j_session.run = AsyncMock(
            side_effect=DriverError("Connection timeout")
        )

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.entities import get_all_entities

            with pytest.raises(HTTPException) as exc_info:
                await get_all_entities(user_id="test-user")

            assert exc_info.value.status_code == 503


# ============================================================================
# Error Response Schema Consistency Tests
# ============================================================================


class TestErrorResponseSchema:
    """Tests for consistent error response schema."""

    def test_http_exception_has_detail(self):
        """HTTPException should always have a detail field."""
        exc = HTTPException(status_code=404, detail="Not found")
        assert hasattr(exc, "detail")
        assert exc.detail == "Not found"

    def test_http_exception_detail_is_string(self):
        """HTTPException detail should be a string for JSON serialization."""
        exc = HTTPException(status_code=400, detail="Invalid input")
        assert isinstance(exc.detail, str)

    @pytest.mark.asyncio
    async def test_404_response_has_detail(self, mock_neo4j_session):
        """404 responses should include detail message."""
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.decisions import get_decision

            with pytest.raises(HTTPException) as exc_info:
                await get_decision(str(uuid4()), user_id="test-user")

            assert exc_info.value.detail is not None
            assert isinstance(exc_info.value.detail, str)
            assert len(exc_info.value.detail) > 0


# ============================================================================
# Rate Limit (429) Tests
# ============================================================================


class TestRateLimitError:
    """Tests for 429 Rate Limit responses."""

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_raises_exception(self):
        """Should raise exception when rate limit exceeded."""
        with patch("services.llm.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch("services.llm.redis") as mock_redis_module:
                mock_redis = AsyncMock()
                mock_pipe = AsyncMock()
                # Always at limit
                mock_pipe.execute = AsyncMock(return_value=[None, 100, None, None])
                mock_redis.pipeline = MagicMock(return_value=mock_pipe)
                mock_redis.zrem = AsyncMock()
                mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                from services.llm import LLMClient

                client = LLMClient()

                with pytest.raises(Exception) as exc_info:
                    await client.generate("Test prompt")

                assert "rate limit" in str(exc_info.value).lower()


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
