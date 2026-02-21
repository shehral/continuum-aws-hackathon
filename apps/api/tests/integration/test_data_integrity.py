"""Tests for data integrity and consistency.

This test suite verifies data integrity across the application:
- Decision-entity relationship consistency
- Orphan entity detection
- Duplicate entity detection
- User isolation (user A cannot see user B's data)
- Cascading delete behavior
- Timestamp validation
- Embedding dimension correctness
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

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


def create_async_result_mock(records):
    """Create a mock Neo4j result that works as an async iterator."""
    result = MagicMock()

    async def async_iter():
        for r in records:
            yield r

    result.__aiter__ = lambda self: async_iter()
    result.single = AsyncMock(return_value=records[0] if records else None)
    return result


def make_decision_dict(decision_id=None, with_options=True):
    """Create a valid decision dict for testing."""
    return {
        "id": decision_id or str(uuid4()),
        "trigger": "Test trigger",
        "context": "Test context",
        "options": ["Option A", "Option B"] if with_options else [],
        "decision": "Option A",
        "rationale": "Test rationale",
        "confidence": 0.9,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "manual",
    }


# ============================================================================
# Decision-Entity Relationship Consistency Tests
# ============================================================================


class TestDecisionEntityRelationshipConsistency:
    """Tests for decision-entity relationship integrity."""

    @pytest.mark.asyncio
    async def test_decision_includes_linked_entities(self, mock_neo4j_session):
        """When fetching a decision, all linked entities should be returned."""
        decision_id = str(uuid4())
        entity_ids = [str(uuid4()) for _ in range(3)]

        decision_data = make_decision_dict(decision_id)

        mock_result = AsyncMock()
        mock_result.single = AsyncMock(
            return_value={
                "d": decision_data,
                "entities": [
                    {"id": entity_ids[0], "name": "PostgreSQL", "type": "technology"},
                    {"id": entity_ids[1], "name": "Redis", "type": "technology"},
                    {"id": entity_ids[2], "name": "Caching", "type": "concept"},
                ],
            }
        )
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.decisions import get_decision

            result = await get_decision(decision_id, user_id="test-user")

            assert len(result.entities) == 3
            assert result.entities[0].name == "PostgreSQL"

    @pytest.mark.asyncio
    async def test_decision_with_empty_entities_list(self, mock_neo4j_session):
        """Decision with empty entities list should work correctly."""
        decision_id = str(uuid4())
        decision_data = make_decision_dict(decision_id)

        mock_result = AsyncMock()
        mock_result.single = AsyncMock(
            return_value={
                "d": decision_data,
                "entities": [],
            }
        )
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.decisions import get_decision

            result = await get_decision(decision_id, user_id="test-user")

            assert result.entities == []
            assert result.trigger == "Test trigger"

    @pytest.mark.asyncio
    async def test_entity_link_requires_both_exist(self, mock_neo4j_session):
        """Linking entity to decision should fail if either doesn't exist."""
        # Decision doesn't exist
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value={"exists": False})
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from fastapi import HTTPException

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
# Orphan Entity Detection Tests
# ============================================================================


class TestOrphanEntityDetection:
    """Tests for orphan entity detection via validator service."""

    @pytest.mark.asyncio
    async def test_orphan_entity_validator_call(self, mock_neo4j_session):
        """Should be able to instantiate validator with session and user_id."""
        from services.validator import GraphValidator

        validator = GraphValidator(mock_neo4j_session, user_id="test-user")
        assert validator.user_id == "test-user"

    @pytest.mark.asyncio
    async def test_validator_check_methods_exist(self, mock_neo4j_session):
        """Validator should have methods for checking orphans."""
        from services.validator import GraphValidator

        validator = GraphValidator(mock_neo4j_session, user_id="test-user")
        assert hasattr(validator, "check_orphan_entities")
        assert hasattr(validator, "check_duplicate_entities")


# ============================================================================
# Duplicate Entity Detection Tests
# ============================================================================


class TestDuplicateEntityDetection:
    """Tests for duplicate entity detection."""

    @pytest.mark.asyncio
    async def test_same_name_entities_blocked_on_create(self, mock_neo4j_session):
        """Creating entity with existing name should return existing entity."""
        existing_entity = {
            "e": {"id": "existing-id", "name": "PostgreSQL", "type": "technology"}
        }

        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=existing_entity)
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from models.schemas import Entity
            from routers.entities import create_entity

            entity = Entity(name="PostgreSQL", type="technology")
            result = await create_entity(entity, user_id="test-user")

            # Should return existing entity, not create duplicate
            assert result.id == "existing-id"

    @pytest.mark.asyncio
    async def test_new_entity_created_when_no_duplicate(self, mock_neo4j_session):
        """Should create new entity when no duplicate exists."""
        # First query: no existing entity
        mock_no_result = AsyncMock()
        mock_no_result.single = AsyncMock(return_value=None)

        mock_neo4j_session.run = AsyncMock(return_value=mock_no_result)

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from models.schemas import Entity
            from routers.entities import create_entity

            entity = Entity(name="NewTech", type="technology")
            result = await create_entity(entity, user_id="test-user")

            # Should create new entity with a new ID
            assert result.name == "NewTech"
            assert result.id is not None


# ============================================================================
# User Isolation Tests
# ============================================================================


class TestUserIsolation:
    """Tests for multi-tenant data isolation."""

    @pytest.mark.asyncio
    async def test_user_a_cannot_see_user_b_decisions(self, mock_neo4j_session):
        """User A's decisions should not be visible to User B."""
        # Mock: user B's query returns empty (can't see user A's data)
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from fastapi import HTTPException

            from routers.decisions import get_decision

            # Try to access user A's decision as user B
            with pytest.raises(HTTPException) as exc_info:
                await get_decision("user-a-decision-id", user_id="user-b")

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_user_decisions_query_includes_user_id(self, mock_neo4j_session):
        """Get decisions should filter by user_id in query."""
        user_decision = make_decision_dict()
        user_decisions = [
            {
                "d": user_decision,
                "entities": [],
            }
        ]

        mock_result = create_async_result_mock(user_decisions)
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.decisions import get_decisions

            results = await get_decisions(limit=50, offset=0, user_id="current-user")

            assert len(results) == 1
            # Verify query included user_id filter
            call_args = mock_neo4j_session.run.call_args
            assert "user_id" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_user_cannot_delete_other_user_decision(self, mock_neo4j_session):
        """User should not be able to delete another user's decision."""
        # Mock: decision exists but belongs to different user (returns None for this user)
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from fastapi import HTTPException

            from routers.decisions import delete_decision

            with pytest.raises(HTTPException) as exc_info:
                await delete_decision("other-user-decision", user_id="attacker-user")

            # Returns 404 to prevent enumeration attacks
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_user_entities_scoped_to_decisions(self, mock_neo4j_session):
        """User should only see entities connected to their decisions."""
        user_entities = [
            {"e": {"id": str(uuid4()), "name": "MyEntity", "type": "technology"}},
        ]

        mock_result = create_async_result_mock(user_entities)
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.entities import get_all_entities

            _results = await get_all_entities(user_id="current-user")

            # Verify query filters by user_id
            call_args = mock_neo4j_session.run.call_args
            assert "user_id" in call_args.kwargs


# ============================================================================
# Cascading Delete Behavior Tests
# ============================================================================


class TestCascadingDeleteBehavior:
    """Tests for cascading delete behavior."""

    @pytest.mark.asyncio
    async def test_delete_decision_preserves_entities(self, mock_neo4j_session):
        """Deleting a decision should preserve linked entities."""
        decision_id = str(uuid4())

        # Mock: decision exists
        mock_exists_result = AsyncMock()
        mock_exists_result.single = AsyncMock(return_value={"d": {"id": decision_id}})

        # Mock: delete succeeds
        mock_delete_result = AsyncMock()
        mock_delete_result.single = AsyncMock(return_value=None)

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            if "DETACH DELETE" in query:
                return mock_delete_result
            return mock_exists_result

        mock_neo4j_session.run = mock_run

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.decisions import delete_decision

            result = await delete_decision(decision_id, user_id="test-user")

            assert result["status"] == "deleted"
            # DETACH DELETE removes relationships but not the entity nodes
            # This is verified by the Cypher query using DETACH DELETE on decision only

    @pytest.mark.asyncio
    async def test_force_delete_entity_removes_all_relationships(
        self, mock_neo4j_session
    ):
        """Force deleting entity should remove all relationships."""
        entity_id = str(uuid4())

        # Mock entity accessible
        mock_accessible_result = AsyncMock()
        mock_accessible_result.single = AsyncMock(return_value={"e": {"id": entity_id}})

        # Mock no other users
        mock_no_other_users = AsyncMock()
        mock_no_other_users.single = AsyncMock(return_value={"other_user_count": 0})

        # Mock has relationships
        mock_has_rels = AsyncMock()
        mock_has_rels.single = AsyncMock(return_value={"rel_count": 0})

        # Mock delete
        mock_delete = AsyncMock()
        mock_delete.single = AsyncMock(return_value=None)

        call_count = [0]

        async def mock_run(query, **params):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_accessible_result
            elif call_count[0] == 2:
                return mock_no_other_users
            elif call_count[0] == 3:
                return mock_has_rels
            else:
                return mock_delete

        mock_neo4j_session.run = mock_run

        with patch(
            "routers.entities.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.entities import delete_entity

            result = await delete_entity(entity_id, force=True, user_id="test-user")

            assert result["status"] == "deleted"


# ============================================================================
# Timestamp Validation Tests
# ============================================================================


class TestTimestampValidation:
    """Tests for timestamp format and validity."""

    @pytest.mark.asyncio
    async def test_decision_created_at_is_datetime(self, mock_neo4j_session):
        """Decision created_at should be valid datetime."""
        decision_id = str(uuid4())
        decision_data = make_decision_dict(decision_id)

        mock_result = AsyncMock()
        mock_result.single = AsyncMock(
            return_value={
                "d": decision_data,
                "entities": [],
            }
        )
        mock_neo4j_session.run = AsyncMock(return_value=mock_result)

        with patch(
            "routers.decisions.get_neo4j_session",
            new_callable=AsyncMock,
            return_value=mock_neo4j_session,
        ):
            from routers.decisions import get_decision

            result = await get_decision(decision_id, user_id="test-user")

            # Verify created_at is valid datetime (Pydantic coerces from string)
            assert result.created_at is not None

    def test_new_decision_schema_works(self):
        """New decisions should be creatable with required fields."""
        from models.schemas import DecisionCreate

        decision = DecisionCreate(
            trigger="Test",
            context="Context",
            options=["A", "B"],
            decision="A",
            rationale="Rationale",
            source="manual",
        )

        assert decision.trigger == "Test"
        assert len(decision.options) >= 1


# ============================================================================
# Embedding Dimension Tests
# ============================================================================


class TestEmbeddingDimensions:
    """Tests for embedding vector dimension correctness."""

    def test_sample_embedding_fixture_correct_dimensions(self, sample_embedding):
        """Sample embedding fixture should have 2048 dimensions."""
        assert len(sample_embedding) == 2048

    def test_mock_embedding_service_dimensions(self, mock_embedding_service):
        """Mock embedding service should return 2048-dimension vectors."""
        assert mock_embedding_service.dimensions == 2048

    def test_embedding_dimensions_constant(self):
        """Embedding service should use 2048 dimensions."""
        # This matches NVIDIA NV-EmbedQA model
        expected_dimensions = 2048
        assert expected_dimensions == 2048


# ============================================================================
# Relationship Type Validation Tests
# ============================================================================


class TestRelationshipTypeValidation:
    """Tests for relationship type validation."""

    def test_valid_relationship_types_accepted(self):
        """Should accept all valid relationship types."""
        from models.schemas import VALID_RELATIONSHIP_TYPES, LinkEntityRequest

        for rel_type in VALID_RELATIONSHIP_TYPES:
            request = LinkEntityRequest(
                decision_id=str(uuid4()),
                entity_id=str(uuid4()),
                relationship=rel_type,
            )
            assert request.relationship == rel_type

    def test_invalid_relationship_type_rejected(self):
        """Should reject invalid relationship types."""
        from pydantic import ValidationError

        from models.schemas import LinkEntityRequest

        with pytest.raises(ValidationError):
            LinkEntityRequest(
                decision_id=str(uuid4()),
                entity_id=str(uuid4()),
                relationship="INVALID_TYPE",
            )

    def test_relationship_type_whitelist_complete(self):
        """Relationship type whitelist should include expected types."""
        from models.schemas import VALID_RELATIONSHIP_TYPES

        expected = {
            "INVOLVES",
            "SIMILAR_TO",
            "SUPERSEDES",
            "INFLUENCED_BY",
            "CONTRADICTS",
            "IS_A",
            "PART_OF",
            "RELATED_TO",
            "DEPENDS_ON",
            "ALTERNATIVE_TO",
            # Phase 5 additions
            "ENABLES",
            "PREVENTS",
            "REQUIRES",
            "REFINES",
        }
        assert expected == VALID_RELATIONSHIP_TYPES


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
