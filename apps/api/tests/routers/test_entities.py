"""Tests for the entities router (SEC-005 compliant)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def create_async_result_mock(records):
    """Create a mock Neo4j result that works as an async iterator."""
    result = MagicMock()

    async def async_iter():
        for r in records:
            yield r

    result.__aiter__ = lambda self: async_iter()
    return result


def create_neo4j_session_mock():
    """Create a mock Neo4j session that works as an async context manager."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


class TestGetAllEntities:
    """Tests for GET / endpoint."""

    @pytest.fixture
    def sample_entities(self):
        """Sample entity records."""
        return [
            {"id": str(uuid4()), "name": "PostgreSQL", "type": "technology"},
            {"id": str(uuid4()), "name": "Redis", "type": "technology"},
            {"id": str(uuid4()), "name": "Microservices", "type": "concept"},
        ]

    @pytest.mark.asyncio
    async def test_get_all_entities_returns_list(self, sample_entities):
        """Should return a list of entities."""
        mock_session = create_neo4j_session_mock()
        mock_session.run = AsyncMock(
            return_value=create_async_result_mock([{"e": e} for e in sample_entities])
        )

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.entities import get_all_entities

            results = await get_all_entities(user_id="test-user")
            assert len(results) == 3
            assert results[0].name == "PostgreSQL"

    @pytest.mark.asyncio
    async def test_get_all_entities_empty(self):
        """Should return empty list when no entities."""
        mock_session = create_neo4j_session_mock()
        mock_session.run = AsyncMock(return_value=create_async_result_mock([]))

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.entities import get_all_entities

            results = await get_all_entities(user_id="test-user")
            assert results == []


class TestGetEntity:
    """Tests for GET /{entity_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_entity_found(self):
        """Should return entity when found."""
        mock_session = create_neo4j_session_mock()
        entity_id = str(uuid4())
        entity_data = {"id": entity_id, "name": "PostgreSQL", "type": "technology"}

        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value={"e": entity_data})
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.entities import get_entity

            result = await get_entity(entity_id, user_id="test-user")
            assert result.id == entity_id
            assert result.name == "PostgreSQL"

    @pytest.mark.asyncio
    async def test_get_entity_not_found(self):
        """Should raise 404 when entity not found."""
        mock_session = create_neo4j_session_mock()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from fastapi import HTTPException

            from routers.entities import get_entity

            with pytest.raises(HTTPException) as exc_info:
                await get_entity("nonexistent-id", user_id="test-user")
            assert exc_info.value.status_code == 404


class TestCreateEntity:
    """Tests for POST / endpoint."""

    @pytest.mark.asyncio
    async def test_create_entity_success(self):
        """Should create and return new entity."""
        mock_session = create_neo4j_session_mock()

        # Mock that no existing entity is found, then create succeeds
        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            result = AsyncMock()
            if "toLower(e.name)" in query:
                # Check for existing entity - none found
                result.single = AsyncMock(return_value=None)
            else:
                # Create new entity
                result.single = AsyncMock(return_value=None)
            return result

        mock_session.run = mock_run

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from models.schemas import Entity
            from routers.entities import create_entity

            new_entity = Entity(name="NewTech", type="technology")
            result = await create_entity(new_entity, user_id="test-user")

            assert result.name == "NewTech"
            assert result.type == "technology"
            assert result.id is not None

    @pytest.mark.asyncio
    async def test_create_entity_with_id(self):
        """Should use provided ID when creating entity."""
        mock_session = create_neo4j_session_mock()
        entity_id = str(uuid4())

        async def mock_run(query, **params):
            result = AsyncMock()
            if "toLower(e.name)" in query:
                # Check for existing entity - none found
                result.single = AsyncMock(return_value=None)
            else:
                result.single = AsyncMock(return_value=None)
            return result

        mock_session.run = mock_run

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from models.schemas import Entity
            from routers.entities import create_entity

            new_entity = Entity(id=entity_id, name="NewTech", type="technology")
            result = await create_entity(new_entity, user_id="test-user")

            assert result.id == entity_id


class TestDeleteEntity:
    """Tests for DELETE /{entity_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_entity_success(self):
        """Should delete entity when it exists and user owns it."""
        mock_session = create_neo4j_session_mock()
        entity_id = str(uuid4())
        entity_data = {"id": entity_id, "name": "OldTech", "type": "technology"}

        # Calls: 1) check user access, 2) check other users, 3) check relationships, 4) delete
        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            result = AsyncMock()
            if (
                "d:DecisionTrace" in query
                and "INVOLVES" in query
                and call_count[0] <= 2
            ):
                if "d.user_id IS NOT NULL AND d.user_id <>" in query:
                    # Check for other users - none
                    result.single = AsyncMock(return_value={"other_user_count": 0})
                else:
                    # Entity is accessible to user
                    result.single = AsyncMock(return_value={"e": entity_data})
            elif "rel_count" in query or "count(r)" in query:
                # No relationships
                result.single = AsyncMock(return_value={"rel_count": 0})
            else:
                # Delete successful
                result.single = AsyncMock(return_value=None)
            return result

        mock_session.run = mock_run

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.entities import delete_entity

            result = await delete_entity(entity_id, user_id="test-user")
            assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_entity_not_found(self):
        """Should raise 404 when entity doesn't exist."""
        mock_session = create_neo4j_session_mock()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from fastapi import HTTPException

            from routers.entities import delete_entity

            with pytest.raises(HTTPException) as exc_info:
                await delete_entity("nonexistent-id", user_id="test-user")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_entity_with_relationships_blocked(self):
        """Should block delete when entity has relationships."""
        mock_session = create_neo4j_session_mock()
        entity_id = str(uuid4())
        entity_data = {"id": entity_id, "name": "LinkedTech", "type": "technology"}

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            result = AsyncMock()
            # Order matters - check most specific patterns first
            if "count(r) as rel_count" in query:
                # Relationship count check - has relationships
                result.single = AsyncMock(return_value={"rel_count": 5})
            elif "other_user_count" in query:
                # Check for other users - none
                result.single = AsyncMock(return_value={"other_user_count": 0})
            elif "RETURN DISTINCT e" in query:
                # Entity accessibility check
                result.single = AsyncMock(return_value={"e": entity_data})
            else:
                result.single = AsyncMock(return_value=None)
            return result

        mock_session.run = mock_run

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from fastapi import HTTPException

            from routers.entities import delete_entity

            with pytest.raises(HTTPException) as exc_info:
                await delete_entity(entity_id, force=False, user_id="test-user")
            assert exc_info.value.status_code == 400
            assert "relationships" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_delete_entity_force(self):
        """Should force delete entity with relationships."""
        mock_session = create_neo4j_session_mock()
        entity_id = str(uuid4())
        entity_data = {"id": entity_id, "name": "LinkedTech", "type": "technology"}

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            result = AsyncMock()
            if "d.user_id IS NOT NULL AND d.user_id <>" in query:
                # Check for other users - none
                result.single = AsyncMock(return_value={"other_user_count": 0})
            elif "d:DecisionTrace" in query and "INVOLVES" in query:
                # Entity is accessible
                result.single = AsyncMock(return_value={"e": entity_data})
            else:
                result.single = AsyncMock(return_value=None)
            return result

        mock_session.run = mock_run

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from routers.entities import delete_entity

            result = await delete_entity(entity_id, force=True, user_id="test-user")
            assert result["status"] == "deleted"


class TestLinkEntity:
    """Tests for POST /link endpoint (SEC-005 compliant with validated UUIDs)."""

    @pytest.mark.asyncio
    async def test_link_entity_success(self):
        """Should link entity to decision with valid UUIDs and relationship type."""
        mock_session = create_neo4j_session_mock()

        # SEC-005: Use valid UUIDs for testing
        decision_id = str(uuid4())
        entity_id = str(uuid4())

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            result = AsyncMock()
            if "count(d) > 0 AS exists" in query:
                # Decision exists check
                result.single = AsyncMock(return_value={"exists": True})
            elif "count(d) > 0 AS accessible" in query:
                # Decision access check - allowed
                result.single = AsyncMock(return_value={"accessible": True})
            elif "count(e) > 0 AS exists" in query:
                # Entity exists check
                result.single = AsyncMock(return_value={"exists": True})
            else:
                # Link successful
                result.single = AsyncMock(return_value=None)
            return result

        mock_session.run = mock_run

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from models.schemas import LinkEntityRequest
            from routers.entities import link_entity

            # SEC-005: Valid UUIDs and relationship type
            request = LinkEntityRequest(
                decision_id=decision_id,
                entity_id=entity_id,
                relationship="INVOLVES",  # Valid relationship type
            )
            result = await link_entity(request, user_id="test-user")
            assert result["status"] == "linked"

    @pytest.mark.asyncio
    async def test_link_entity_invalid_uuid_format(self):
        """SEC-005: Should reject invalid UUID format."""
        from pydantic import ValidationError

        from models.schemas import LinkEntityRequest

        with pytest.raises(ValidationError) as exc_info:
            LinkEntityRequest(
                decision_id="not-a-uuid",  # Invalid
                entity_id=str(uuid4()),
                relationship="INVOLVES",
            )

        # Check that the error mentions the decision_id field
        errors = exc_info.value.errors()
        assert any("decision_id" in str(e) for e in errors)

    @pytest.mark.asyncio
    async def test_link_entity_invalid_relationship_type(self):
        """SEC-005: Should reject invalid relationship type."""
        from pydantic import ValidationError

        from models.schemas import LinkEntityRequest

        with pytest.raises(ValidationError) as exc_info:
            LinkEntityRequest(
                decision_id=str(uuid4()),
                entity_id=str(uuid4()),
                relationship="INVALID_TYPE",  # Invalid relationship
            )

        # Check that the error mentions the relationship field
        errors = exc_info.value.errors()
        assert any("relationship" in str(e) for e in errors)

    @pytest.mark.asyncio
    async def test_link_entity_decision_not_found(self):
        """Should return 404 when decision doesn't exist."""
        mock_session = create_neo4j_session_mock()
        decision_id = str(uuid4())
        entity_id = str(uuid4())

        async def mock_run(query, **params):
            result = AsyncMock()
            if "count(d) > 0 AS exists" in query:
                # Decision doesn't exist
                result.single = AsyncMock(return_value={"exists": False})
            return result

        mock_session.run = mock_run

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from fastapi import HTTPException

            from models.schemas import LinkEntityRequest
            from routers.entities import link_entity

            request = LinkEntityRequest(
                decision_id=decision_id,
                entity_id=entity_id,
                relationship="INVOLVES",
            )

            with pytest.raises(HTTPException) as exc_info:
                await link_entity(request, user_id="test-user")
            assert exc_info.value.status_code == 404
            assert "Decision not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_link_entity_entity_not_found(self):
        """Should return 404 when entity doesn't exist."""
        mock_session = create_neo4j_session_mock()
        decision_id = str(uuid4())
        entity_id = str(uuid4())

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            result = AsyncMock()
            if "count(d) > 0 AS exists" in query:
                # Decision exists
                result.single = AsyncMock(return_value={"exists": True})
            elif "count(d) > 0 AS accessible" in query:
                # Decision accessible
                result.single = AsyncMock(return_value={"accessible": True})
            elif "count(e) > 0 AS exists" in query:
                # Entity doesn't exist
                result.single = AsyncMock(return_value={"exists": False})
            return result

        mock_session.run = mock_run

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            from fastapi import HTTPException

            from models.schemas import LinkEntityRequest
            from routers.entities import link_entity

            request = LinkEntityRequest(
                decision_id=decision_id,
                entity_id=entity_id,
                relationship="INVOLVES",
            )

            with pytest.raises(HTTPException) as exc_info:
                await link_entity(request, user_id="test-user")
            assert exc_info.value.status_code == 404
            assert "Entity not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_link_entity_case_insensitive_relationship(self):
        """SEC-005: Relationship types should be case-insensitive (converted to uppercase)."""
        from models.schemas import LinkEntityRequest

        request = LinkEntityRequest(
            decision_id=str(uuid4()),
            entity_id=str(uuid4()),
            relationship="involves",  # lowercase
        )

        # Should be converted to uppercase
        assert request.relationship == "INVOLVES"


class TestSuggestEntities:
    """Tests for POST /suggest endpoint."""

    @pytest.mark.asyncio
    async def test_suggest_entities_returns_suggestions(self):
        """Should return entity suggestions based on text."""
        mock_session = create_neo4j_session_mock()
        mock_extractor = AsyncMock()

        # Mock extracted entities
        mock_extractor.extract_entities = AsyncMock(
            return_value=[
                {"name": "PostgreSQL", "type": "technology"},
                {"name": "Redis", "type": "technology"},
            ]
        )

        # Mock database lookup returns some existing matches
        async def mock_result_iter():
            yield {
                "e": {"id": str(uuid4()), "name": "PostgreSQL", "type": "technology"}
            }

        mock_result = MagicMock()
        mock_result.__aiter__ = lambda self: mock_result_iter()
        mock_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_session,
        ):
            with patch(
                "routers.entities.DecisionExtractor",
                return_value=mock_extractor,
            ):
                from models.schemas import SuggestEntitiesRequest
                from routers.entities import suggest_entities

                request = SuggestEntitiesRequest(
                    text="Using PostgreSQL and Redis for data storage"
                )
                results = await suggest_entities(request, user_id="test-user")

                # Should have both existing and new suggestions
                assert len(results) >= 1
                names = [e.name for e in results]
                assert "PostgreSQL" in names
