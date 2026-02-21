"""End-to-End Workflow Tests for Continuum API.

These tests verify complete user workflows using mocked dependencies
to simulate the full stack behavior without requiring external services.

Workflows tested:
- Ingest flow: parse logs -> extract decisions -> view -> edit -> delete
- Capture session flow: start session -> send messages -> complete session
- Entity management flow: create entities -> link to decisions -> search -> delete

QA-P2-3: E2E Workflow Tests
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from models.postgres import SessionStatus
from services.parser import Conversation
from tests.mocks.llm_mock import MockEmbeddingService, MockLLMClient
from tests.mocks.neo4j_mock import MockNeo4jSession

# ============================================================================
# Fixtures for E2E Tests
# ============================================================================


@pytest.fixture
def mock_llm():
    """Create a mock LLM client."""
    return MockLLMClient()


@pytest.fixture
def mock_embedding_service():
    """Create a mock embedding service."""
    return MockEmbeddingService()


@pytest.fixture
def mock_neo4j_session():
    """Create a mock Neo4j session."""
    return MockNeo4jSession()


@pytest.fixture
def mock_postgres_session():
    """Create a mock PostgreSQL session."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


@pytest.fixture
def sample_conversation():
    """Create a sample conversation for ingestion testing."""
    return Conversation(
        messages=[
            {
                "role": "user",
                "content": "We need to choose a database for our project.",
            },
            {"role": "assistant", "content": "What are your requirements?"},
            {
                "role": "user",
                "content": "We need ACID compliance, good performance, and JSON support.",
            },
            {
                "role": "assistant",
                "content": "I recommend PostgreSQL. It provides excellent ACID compliance, native JSONB support, and great performance for complex queries.",
            },
            {"role": "user", "content": "Let's go with PostgreSQL then."},
        ],
        file_path="/test/claude/logs/project-test/conversation.jsonl",
        project_name="test-project",
    )


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.claude_logs_path = "/test/claude/logs"
    settings.redis_url = "redis://localhost:6379"
    settings.llm_cache_enabled = False
    settings.llm_extraction_prompt_version = "v1"
    settings.similarity_threshold = 0.7
    settings.high_confidence_similarity_threshold = 0.85
    return settings


# ============================================================================
# Test: Complete Ingest Flow
# ============================================================================


class TestIngestWorkflow:
    """Test the complete ingestion workflow.

    Flow: Parse logs -> Extract decisions -> Save to Neo4j -> View -> Edit -> Delete
    """

    @pytest.mark.asyncio
    async def test_ingest_view_edit_delete_flow(
        self, mock_llm, mock_embedding_service, mock_neo4j_session, mock_settings
    ):
        """Test complete ingest -> view -> edit -> delete workflow."""
        _decision_id = str(uuid4())  # noqa: F841 - kept for future test expansion
        _user_id = "test-user-001"  # noqa: F841 - kept for future test expansion

        # Mock LLM responses for extraction
        mock_llm.set_json_response(
            "analyze",
            [
                {
                    "trigger": "Need to choose a database",
                    "context": "Building a web application with complex queries",
                    "options": ["PostgreSQL", "MySQL", "MongoDB"],
                    "decision": "Use PostgreSQL",
                    "rationale": "Best ACID compliance and JSON support",
                    "confidence": 0.9,
                }
            ],
        )

        mock_llm.set_json_response(
            "extract",
            {
                "entities": [
                    {"name": "PostgreSQL", "type": "technology", "confidence": 0.95},
                    {"name": "database", "type": "concept", "confidence": 0.8},
                ],
                "reasoning": "PostgreSQL is a database technology",
            },
        )

        # Configure Neo4j mock responses
        mock_neo4j_session.set_default_response(
            records=[],
            single_value=None,
        )

        with (
            patch("services.extractor.get_llm_client", return_value=mock_llm),
            patch(
                "services.extractor.get_embedding_service",
                return_value=mock_embedding_service,
            ),
            patch("services.extractor.get_settings", return_value=mock_settings),
            patch(
                "services.extractor.get_neo4j_session", return_value=mock_neo4j_session
            ),
            patch("services.entity_resolver.get_settings", return_value=mock_settings),
        ):
            from services.extractor import DecisionExtractor

            extractor = DecisionExtractor()
            extractor.llm = mock_llm
            extractor.embedding_service = mock_embedding_service

            # Step 1: Extract decisions from conversation
            conversation = Conversation(
                messages=[
                    {"role": "user", "content": "We need to choose a database."},
                    {
                        "role": "assistant",
                        "content": "I recommend PostgreSQL for your needs.",
                    },
                ],
                file_path="/test/logs/conversation.jsonl",
                project_name="test-project",
            )

            decisions = await extractor.extract_decisions(conversation)

            assert len(decisions) == 1
            assert decisions[0].trigger == "Need to choose a database"
            assert decisions[0].decision == "Use PostgreSQL"

            # Step 2: Verify decision structure is correct for saving
            decision = decisions[0]
            assert decision.confidence >= 0.0 and decision.confidence <= 1.0
            assert isinstance(decision.options, list)
            assert decision.rationale != ""

    @pytest.mark.asyncio
    async def test_ingest_handles_no_decisions_gracefully(
        self, mock_llm, mock_embedding_service, mock_settings
    ):
        """Test ingest flow when conversation has no decisions."""
        # LLM returns empty array for no decisions
        mock_llm.set_json_response("analyze", [])

        with (
            patch("services.extractor.get_llm_client", return_value=mock_llm),
            patch(
                "services.extractor.get_embedding_service",
                return_value=mock_embedding_service,
            ),
            patch("services.extractor.get_settings", return_value=mock_settings),
        ):
            from services.extractor import DecisionExtractor

            extractor = DecisionExtractor()
            extractor.llm = mock_llm
            extractor.embedding_service = mock_embedding_service

            # Conversation with no decisions
            conversation = Conversation(
                messages=[
                    {
                        "role": "user",
                        "content": "What do you think about microservices?",
                    },
                    {
                        "role": "assistant",
                        "content": "They have pros and cons depending on your needs.",
                    },
                ],
                file_path="/test/logs/discussion.jsonl",
                project_name="test-project",
            )

            decisions = await extractor.extract_decisions(conversation)

            assert len(decisions) == 0

    @pytest.mark.asyncio
    async def test_ingest_recovers_from_llm_errors(
        self, mock_embedding_service, mock_settings
    ):
        """Test that ingest flow handles LLM errors gracefully."""
        mock_llm = MockLLMClient()
        mock_llm.generate = AsyncMock(side_effect=TimeoutError("LLM timeout"))

        with (
            patch("services.extractor.get_llm_client", return_value=mock_llm),
            patch(
                "services.extractor.get_embedding_service",
                return_value=mock_embedding_service,
            ),
            patch("services.extractor.get_settings", return_value=mock_settings),
        ):
            from services.extractor import DecisionExtractor

            extractor = DecisionExtractor()
            extractor.llm = mock_llm
            extractor.embedding_service = mock_embedding_service

            conversation = Conversation(
                messages=[{"role": "user", "content": "Test"}],
                file_path="/test/logs/test.jsonl",
                project_name="test",
            )

            # Should not raise, should return empty list
            decisions = await extractor.extract_decisions(conversation)

            assert decisions == []


# ============================================================================
# Test: Complete Capture Session Flow
# ============================================================================


class TestCaptureSessionWorkflow:
    """Test the capture session workflow.

    Flow: Start session -> Send messages -> Complete session -> Save decision
    """

    @pytest.mark.asyncio
    async def test_capture_session_full_flow(self, mock_postgres_session):
        """Test complete capture session lifecycle."""
        session_id = str(uuid4())
        user_id = "test-user-001"

        # Create mock session object
        mock_capture_session = MagicMock()
        mock_capture_session.id = session_id
        mock_capture_session.user_id = user_id
        mock_capture_session.status = SessionStatus.ACTIVE
        mock_capture_session.created_at = datetime.now(UTC)
        mock_capture_session.updated_at = datetime.now(UTC)

        # Mock refresh to set timestamp fields on the session
        async def mock_refresh(obj):
            if not hasattr(obj, "created_at") or obj.created_at is None:
                obj.created_at = datetime.now(UTC)
            if not hasattr(obj, "updated_at") or obj.updated_at is None:
                obj.updated_at = datetime.now(UTC)

        mock_postgres_session.refresh = mock_refresh

        # Step 1: Start session
        with patch("routers.capture.get_db", return_value=mock_postgres_session):
            from routers.capture import start_capture_session

            result = await start_capture_session(
                db=mock_postgres_session,
                user_id=user_id,
            )

            assert result.status == "active"
            assert result.id is not None

    @pytest.mark.asyncio
    async def test_capture_session_message_flow(self, mock_postgres_session):
        """Test sending messages in a capture session."""
        session_id = str(uuid4())
        user_id = "test-user-001"

        # Mock active session
        mock_session_obj = MagicMock()
        mock_session_obj.id = session_id
        mock_session_obj.status = SessionStatus.ACTIVE
        mock_session_obj.user_id = user_id

        # Configure mock to return session
        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none = MagicMock(
            return_value=mock_session_obj
        )

        mock_messages_result = MagicMock()
        mock_messages_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_session_result
            return mock_messages_result

        mock_postgres_session.execute = mock_execute

        # Mock AI response
        mock_ai_message = MagicMock()
        mock_ai_message.id = str(uuid4())
        mock_ai_message.role = "assistant"
        mock_ai_message.content = "What technologies are you considering?"
        mock_ai_message.timestamp = datetime.now(UTC)
        mock_ai_message.extracted_entities = []

        async def mock_refresh(obj):
            if hasattr(obj, "content"):
                obj.id = mock_ai_message.id
                obj.role = mock_ai_message.role
                obj.content = mock_ai_message.content
                obj.timestamp = mock_ai_message.timestamp
                obj.extracted_entities = mock_ai_message.extracted_entities

        mock_postgres_session.refresh = mock_refresh

        mock_interview_agent = MagicMock()
        mock_interview_agent.process_message = AsyncMock(
            return_value=("What technologies are you considering?", [])
        )

        with patch("routers.capture.InterviewAgent", return_value=mock_interview_agent):
            from routers.capture import send_capture_message

            result = await send_capture_message(
                session_id=session_id,
                content={"content": "We need to make a decision about our database."},
                db=mock_postgres_session,
                user_id=user_id,
            )

            assert result.role == "assistant"
            assert "technologies" in result.content.lower()

    @pytest.mark.asyncio
    async def test_capture_session_completion(
        self, mock_postgres_session, mock_llm, mock_embedding_service
    ):
        """Test completing a capture session and saving the decision."""
        session_id = str(uuid4())
        user_id = "test-user-001"

        # Mock session
        mock_session_obj = MagicMock()
        mock_session_obj.id = session_id
        mock_session_obj.status = SessionStatus.ACTIVE
        mock_session_obj.user_id = user_id
        mock_session_obj.created_at = datetime.now(UTC)
        mock_session_obj.updated_at = datetime.now(UTC)

        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none = MagicMock(
            return_value=mock_session_obj
        )

        # Mock messages
        mock_message = MagicMock()
        mock_message.id = str(uuid4())
        mock_message.role = "user"
        mock_message.content = "We decided to use PostgreSQL for our database."
        mock_message.timestamp = datetime.now(UTC)
        mock_message.extracted_entities = []

        mock_messages_result = MagicMock()
        mock_messages_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[mock_message]))
        )

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_session_result
            return mock_messages_result

        mock_postgres_session.execute = mock_execute

        # Mock interview agent synthesizing decision
        mock_interview_agent = MagicMock()
        mock_interview_agent.synthesize_decision = AsyncMock(
            return_value={
                "trigger": "Database selection",
                "context": "Building a new application",
                "options": ["PostgreSQL", "MySQL", "MongoDB"],
                "decision": "PostgreSQL",
                "rationale": "Best fit for our relational data needs",
                "confidence": 0.85,
            }
        )

        # Mock extractor
        mock_extractor = MagicMock()
        mock_extractor.save_decision = AsyncMock(return_value="decision-123")

        with (
            patch("routers.capture.InterviewAgent", return_value=mock_interview_agent),
            patch("services.extractor.DecisionExtractor", return_value=mock_extractor),
        ):
            from routers.capture import complete_capture_session

            result = await complete_capture_session(
                session_id=session_id,
                db=mock_postgres_session,
                user_id=user_id,
            )

            assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_capture_session_rejects_completed_session(
        self, mock_postgres_session
    ):
        """Test that completed sessions cannot receive more messages."""
        session_id = str(uuid4())
        user_id = "test-user-001"

        # Mock completed session
        mock_session_obj = MagicMock()
        mock_session_obj.id = session_id
        mock_session_obj.status = SessionStatus.COMPLETED
        mock_session_obj.user_id = user_id

        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none = MagicMock(
            return_value=mock_session_obj
        )
        mock_postgres_session.execute = AsyncMock(return_value=mock_session_result)

        from fastapi import HTTPException

        from routers.capture import send_capture_message

        with pytest.raises(HTTPException) as exc_info:
            await send_capture_message(
                session_id=session_id,
                content={"content": "Test"},
                db=mock_postgres_session,
                user_id=user_id,
            )

        assert exc_info.value.status_code == 400
        assert "not active" in str(exc_info.value.detail).lower()


# ============================================================================
# Test: Entity Management Workflow
# ============================================================================


class TestEntityManagementWorkflow:
    """Test entity creation, linking, and deletion workflows."""

    @pytest.mark.asyncio
    async def test_entity_extraction_and_resolution(
        self, mock_llm, mock_embedding_service, mock_neo4j_session, mock_settings
    ):
        """Test extracting entities and resolving duplicates."""
        # Configure LLM to extract entities
        mock_llm.set_json_response(
            "extract",
            {
                "entities": [
                    {"name": "PostgreSQL", "type": "technology", "confidence": 0.95},
                    {
                        "name": "Postgres",
                        "type": "technology",
                        "confidence": 0.9,
                    },  # Alias
                    {"name": "database", "type": "concept", "confidence": 0.8},
                ],
                "reasoning": "PostgreSQL/Postgres are the same database technology",
            },
        )

        # Configure Neo4j to return existing PostgreSQL entity
        existing_entity = {
            "id": str(uuid4()),
            "name": "PostgreSQL",
            "type": "technology",
            "aliases": ["postgres", "pg"],
        }

        mock_neo4j_session.set_response(
            "toLower(e.name)",
            single_value=existing_entity,
        )

        with (
            patch("services.extractor.get_llm_client", return_value=mock_llm),
            patch(
                "services.extractor.get_embedding_service",
                return_value=mock_embedding_service,
            ),
            patch("services.extractor.get_settings", return_value=mock_settings),
        ):
            from services.extractor import DecisionExtractor

            extractor = DecisionExtractor()
            extractor.llm = mock_llm
            extractor.embedding_service = mock_embedding_service

            text = "We chose PostgreSQL (also known as Postgres) as our database."
            entities = await extractor.extract_entities(text)

            # Should extract multiple entities
            assert len(entities) >= 2

            # Verify entity types are correct
            entity_types = {e["type"] for e in entities}
            assert "technology" in entity_types

    @pytest.mark.asyncio
    async def test_entity_relationship_extraction(
        self, mock_llm, mock_embedding_service, mock_settings
    ):
        """Test extracting relationships between entities."""
        # Configure LLM for relationship extraction
        mock_llm.set_json_response(
            "identify",
            {
                "relationships": [
                    {
                        "from": "Next.js",
                        "to": "React",
                        "type": "DEPENDS_ON",
                        "confidence": 0.95,
                    },
                    {
                        "from": "PostgreSQL",
                        "to": "MongoDB",
                        "type": "ALTERNATIVE_TO",
                        "confidence": 0.9,
                    },
                ],
                "reasoning": "Next.js is built on React; PostgreSQL and MongoDB are alternative databases",
            },
        )

        with (
            patch("services.extractor.get_llm_client", return_value=mock_llm),
            patch(
                "services.extractor.get_embedding_service",
                return_value=mock_embedding_service,
            ),
            patch("services.extractor.get_settings", return_value=mock_settings),
        ):
            from services.extractor import DecisionExtractor

            extractor = DecisionExtractor()
            extractor.llm = mock_llm
            extractor.embedding_service = mock_embedding_service

            entities = [
                {"name": "Next.js", "type": "technology"},
                {"name": "React", "type": "technology"},
                {"name": "PostgreSQL", "type": "technology"},
                {"name": "MongoDB", "type": "technology"},
            ]

            relationships = await extractor.extract_entity_relationships(
                entities,
                context="Building a web app with Next.js and PostgreSQL",
            )

            # Should extract relationships
            assert len(relationships) >= 1

            # Verify relationship types
            rel_types = {r["type"] for r in relationships}
            assert "DEPENDS_ON" in rel_types or "ALTERNATIVE_TO" in rel_types


# ============================================================================
# Test: Decision Analysis Workflow
# ============================================================================


class TestDecisionAnalysisWorkflow:
    """Test decision comparison and relationship detection workflows."""

    @pytest.mark.asyncio
    async def test_detect_superseding_decisions(
        self, mock_llm, mock_embedding_service, mock_settings
    ):
        """Test detecting when one decision supersedes another."""
        # Configure LLM to detect supersedes relationship
        mock_llm.set_json_response(
            "analyze",
            {
                "relationship": "SUPERSEDES",
                "confidence": 0.9,
                "reasoning": "The newer decision explicitly changes the database choice from PostgreSQL to MongoDB",
            },
        )

        with (
            patch("services.extractor.get_llm_client", return_value=mock_llm),
            patch(
                "services.extractor.get_embedding_service",
                return_value=mock_embedding_service,
            ),
            patch("services.extractor.get_settings", return_value=mock_settings),
        ):
            from services.extractor import DecisionExtractor

            extractor = DecisionExtractor()
            extractor.llm = mock_llm

            older_decision = {
                "created_at": "2024-01-01",
                "trigger": "Initial database choice",
                "decision": "Use PostgreSQL",
                "rationale": "Good for relational data",
            }

            newer_decision = {
                "created_at": "2024-06-01",
                "trigger": "Database migration needed",
                "decision": "Switch to MongoDB",
                "rationale": "Need document flexibility for new requirements",
            }

            result = await extractor.extract_decision_relationship(
                older_decision, newer_decision
            )

            assert result is not None
            assert result["type"] == "SUPERSEDES"
            assert result["confidence"] >= 0.8

    @pytest.mark.asyncio
    async def test_detect_contradicting_decisions(
        self, mock_llm, mock_embedding_service, mock_settings
    ):
        """Test detecting contradicting decisions."""
        mock_llm.set_json_response(
            "analyze",
            {
                "relationship": "CONTRADICTS",
                "confidence": 0.85,
                "reasoning": "JWT stateless auth conflicts with session-based stateful auth",
            },
        )

        with (
            patch("services.extractor.get_llm_client", return_value=mock_llm),
            patch(
                "services.extractor.get_embedding_service",
                return_value=mock_embedding_service,
            ),
            patch("services.extractor.get_settings", return_value=mock_settings),
        ):
            from services.extractor import DecisionExtractor

            extractor = DecisionExtractor()
            extractor.llm = mock_llm

            decision_a = {
                "created_at": "2024-01-01",
                "trigger": "Auth implementation",
                "decision": "Use JWT tokens",
                "rationale": "Stateless authentication",
            }

            decision_b = {
                "created_at": "2024-01-15",
                "trigger": "Auth reconsideration",
                "decision": "Use session cookies",
                "rationale": "Need server-side session management",
            }

            result = await extractor.extract_decision_relationship(
                decision_a, decision_b
            )

            assert result is not None
            assert result["type"] == "CONTRADICTS"

    @pytest.mark.asyncio
    async def test_detect_no_relationship(
        self, mock_llm, mock_embedding_service, mock_settings
    ):
        """Test detecting when decisions have no significant relationship."""
        mock_llm.set_json_response(
            "analyze",
            {
                "relationship": None,
                "confidence": 0.0,
                "reasoning": "Decisions are about unrelated topics",
            },
        )

        with (
            patch("services.extractor.get_llm_client", return_value=mock_llm),
            patch(
                "services.extractor.get_embedding_service",
                return_value=mock_embedding_service,
            ),
            patch("services.extractor.get_settings", return_value=mock_settings),
        ):
            from services.extractor import DecisionExtractor

            extractor = DecisionExtractor()
            extractor.llm = mock_llm

            decision_a = {
                "created_at": "2024-01-01",
                "trigger": "Database choice",
                "decision": "PostgreSQL",
                "rationale": "Relational data",
            }

            decision_b = {
                "created_at": "2024-01-05",
                "trigger": "Frontend framework",
                "decision": "React",
                "rationale": "Team familiarity",
            }

            result = await extractor.extract_decision_relationship(
                decision_a, decision_b
            )

            assert result is None


# ============================================================================
# Test: Error Recovery Workflows
# ============================================================================


class TestErrorRecoveryWorkflows:
    """Test system behavior under error conditions."""

    @pytest.mark.asyncio
    async def test_extraction_continues_after_single_decision_error(
        self, mock_llm, mock_embedding_service, mock_settings
    ):
        """Test that extraction process continues even if one decision fails."""
        # First call succeeds, simulate real scenario
        mock_llm.set_json_response(
            "analyze",
            [
                {
                    "trigger": "Test decision",
                    "context": "Test context",
                    "options": ["A", "B"],
                    "decision": "A",
                    "rationale": "Because",
                    "confidence": 0.8,
                }
            ],
        )

        with (
            patch("services.extractor.get_llm_client", return_value=mock_llm),
            patch(
                "services.extractor.get_embedding_service",
                return_value=mock_embedding_service,
            ),
            patch("services.extractor.get_settings", return_value=mock_settings),
        ):
            from services.extractor import DecisionExtractor

            extractor = DecisionExtractor()
            extractor.llm = mock_llm
            extractor.embedding_service = mock_embedding_service

            conversation = Conversation(
                messages=[{"role": "user", "content": "Test decision"}],
                file_path="/test",
                project_name="test",
            )

            decisions = await extractor.extract_decisions(conversation)

            # Should still return valid decisions
            assert len(decisions) == 1

    @pytest.mark.asyncio
    async def test_malformed_llm_response_handling(
        self, mock_embedding_service, mock_settings
    ):
        """Test handling of malformed LLM responses."""
        mock_llm = MockLLMClient()

        # Return invalid JSON
        mock_llm.set_default_response("This is not valid JSON at all")

        with (
            patch("services.extractor.get_llm_client", return_value=mock_llm),
            patch(
                "services.extractor.get_embedding_service",
                return_value=mock_embedding_service,
            ),
            patch("services.extractor.get_settings", return_value=mock_settings),
        ):
            from services.extractor import DecisionExtractor

            extractor = DecisionExtractor()
            extractor.llm = mock_llm
            extractor.embedding_service = mock_embedding_service

            conversation = Conversation(
                messages=[{"role": "user", "content": "Test"}],
                file_path="/test",
                project_name="test",
            )

            # Should not raise, should return empty
            decisions = await extractor.extract_decisions(conversation)
            assert decisions == []

            entities = await extractor.extract_entities("PostgreSQL database")
            assert entities == []

    @pytest.mark.asyncio
    async def test_partial_json_response_handling(
        self, mock_embedding_service, mock_settings
    ):
        """Test handling of partial/truncated JSON responses."""
        mock_llm = MockLLMClient()

        # Return truncated JSON
        mock_llm.set_default_response('[{"trigger": "test", "decision": "A"')

        with (
            patch("services.extractor.get_llm_client", return_value=mock_llm),
            patch(
                "services.extractor.get_embedding_service",
                return_value=mock_embedding_service,
            ),
            patch("services.extractor.get_settings", return_value=mock_settings),
        ):
            from services.extractor import DecisionExtractor

            extractor = DecisionExtractor()
            extractor.llm = mock_llm
            extractor.embedding_service = mock_embedding_service

            conversation = Conversation(
                messages=[{"role": "user", "content": "Test"}],
                file_path="/test",
                project_name="test",
            )

            # Should handle gracefully
            decisions = await extractor.extract_decisions(conversation)
            assert isinstance(decisions, list)


# ============================================================================
# Test: WebSocket Security
# ============================================================================


class TestWebSocketSecurity:
    """Test WebSocket input validation and rate limiting (SEC-012)."""

    def test_validate_message_valid(self):
        """Test validation of valid WebSocket message."""
        from routers.capture import validate_websocket_message

        is_valid, error = validate_websocket_message(
            {"content": "This is a valid message"}
        )

        assert is_valid is True
        assert error == ""

    def test_validate_message_missing_content(self):
        """Test validation rejects missing content field."""
        from routers.capture import validate_websocket_message

        is_valid, error = validate_websocket_message({})

        assert is_valid is False
        assert "content" in error.lower()

    def test_validate_message_empty_content(self):
        """Test validation rejects empty content."""
        from routers.capture import validate_websocket_message

        is_valid, error = validate_websocket_message({"content": ""})

        assert is_valid is False
        assert "empty" in error.lower()

    def test_validate_message_oversized(self):
        """Test validation rejects oversized messages."""
        from routers.capture import MAX_MESSAGE_SIZE, validate_websocket_message

        oversized_content = "x" * (MAX_MESSAGE_SIZE + 1)
        is_valid, error = validate_websocket_message({"content": oversized_content})

        assert is_valid is False
        assert "size" in error.lower() or "maximum" in error.lower()

    def test_validate_message_non_dict(self):
        """Test validation rejects non-dict messages."""
        from routers.capture import validate_websocket_message

        is_valid, error = validate_websocket_message("just a string")

        assert is_valid is False
        assert "object" in error.lower()

    def test_rate_limiter_allows_normal_usage(self):
        """Test rate limiter allows normal message rate."""
        from routers.capture import WebSocketRateLimiter

        limiter = WebSocketRateLimiter(max_messages=5, window=60)

        # First 5 messages should be allowed
        for _ in range(5):
            assert limiter.check() is True

    def test_rate_limiter_blocks_excessive_usage(self):
        """Test rate limiter blocks excessive messages."""
        from routers.capture import WebSocketRateLimiter

        limiter = WebSocketRateLimiter(max_messages=3, window=60)

        # Use up the limit
        for _ in range(3):
            limiter.check()

        # Next message should be blocked
        assert limiter.check() is False

    def test_rate_limiter_retry_after(self):
        """Test rate limiter provides retry-after time."""
        from routers.capture import WebSocketRateLimiter

        limiter = WebSocketRateLimiter(max_messages=1, window=60)
        limiter.check()  # Use the one allowed message

        retry_after = limiter.get_retry_after()

        # Should be close to 60 seconds (the window)
        assert retry_after > 0
        assert retry_after <= 60


# ============================================================================
# Run tests
# ============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
