"""Comprehensive unit tests for DecisionExtractor service.

Tests:
- Decision extraction from conversations
- Entity extraction from text
- Entity relationship extraction
- Decision relationship analysis (SUPERSEDES/CONTRADICTS)
- Error handling for malformed input
- Caching behavior
- Confidence calibration

Target: 85%+ coverage for extractor.py
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from services.extractor import (
    DecisionExtractor,
    DecisionType,
    LLMResponseCache,
    apply_decision_defaults,
    calibrate_confidence,
    detect_decision_type,
    get_extractor,
)
from services.parser import Conversation
from tests.mocks.llm_mock import MockEmbeddingService, MockLLMClient
from tests.mocks.neo4j_mock import MockNeo4jSession

# ============================================================================
# Test Fixtures
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
def mock_redis():
    """Create a mock Redis client for caching."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock(return_value=True)
    redis.ping = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def extractor_with_mocks(mock_llm, mock_embedding_service):
    """Create DecisionExtractor with mocked dependencies and disabled cache."""
    with (
        patch("services.extractor.get_llm_client", return_value=mock_llm),
        patch(
            "services.extractor.get_embedding_service",
            return_value=mock_embedding_service,
        ),
        patch("services.extractor.get_settings") as mock_settings,
    ):
        mock_settings.return_value.llm_cache_enabled = False  # Disable cache for tests
        mock_settings.return_value.similarity_threshold = 0.7
        mock_settings.return_value.high_confidence_similarity_threshold = 0.85
        extractor = DecisionExtractor()
        extractor.llm = mock_llm
        extractor.embedding_service = mock_embedding_service
        return extractor


@pytest.fixture
def sample_conversation():
    """Create a sample conversation for testing."""
    messages = [
        {"role": "user", "content": "We need to choose a database for our project."},
        {"role": "assistant", "content": "What are your main requirements?"},
        {"role": "user", "content": "We need ACID compliance and good JSON support."},
        {
            "role": "assistant",
            "content": "I recommend PostgreSQL for those requirements.",
        },
    ]
    return Conversation(
        messages=messages,
        file_path="/test/path/conversation.jsonl",
        project_name="test-project",
    )


def create_unique_conversation(unique_id: str) -> Conversation:
    """Create a conversation with unique text to avoid cache hits."""
    messages = [
        {"role": "user", "content": f"Unique content {unique_id} for testing"},
        {"role": "assistant", "content": f"Response for {unique_id}"},
    ]
    return Conversation(
        messages=messages,
        file_path=f"/test/path/{unique_id}.jsonl",
        project_name="test-project",
    )


# ============================================================================
# Decision Type Detection Tests
# ============================================================================


class TestDecisionTypeDetection:
    """Test decision type auto-detection from text."""

    def test_detect_architecture_type(self):
        """Should detect architecture decision type."""
        text = "We decided on a microservices architecture for better scalability"
        result = detect_decision_type(text)
        assert result == DecisionType.ARCHITECTURE

    def test_detect_technology_type(self):
        """Should detect technology decision type."""
        text = "We chose PostgreSQL as the database and React for the frontend"
        result = detect_decision_type(text)
        assert result == DecisionType.TECHNOLOGY

    def test_detect_process_type(self):
        """Should detect process decision type."""
        text = "We implemented CI/CD pipeline with code review workflow"
        result = detect_decision_type(text)
        assert result == DecisionType.PROCESS

    def test_detect_general_type_when_unclear(self):
        """Should default to general when no clear type."""
        text = "We made a decision about something"
        result = detect_decision_type(text)
        assert result == DecisionType.GENERAL

    def test_detect_with_multiple_keywords(self):
        """Should pick the type with most keyword matches."""
        text = "Using Docker and Kubernetes for microservices deployment in our architecture"
        result = detect_decision_type(text)
        # Should detect as architecture (has microservices, architecture)
        # or technology (has docker, kubernetes)
        assert result in [DecisionType.ARCHITECTURE, DecisionType.TECHNOLOGY]

    def test_detect_is_case_insensitive(self):
        """Should detect keywords regardless of case."""
        text = "POSTGRESQL DATABASE with DOCKER containers"
        result = detect_decision_type(text)
        assert result == DecisionType.TECHNOLOGY


# ============================================================================
# Confidence Calibration Tests
# ============================================================================


class TestConfidenceCalibration:
    """Test confidence calibration based on extraction quality."""

    def test_calibrate_complete_decision(self):
        """Should boost confidence for complete decisions."""
        decision = {
            "trigger": "Need to choose a database",
            "context": "Building a web application with complex queries",
            "options": ["PostgreSQL", "MongoDB", "MySQL"],
            "decision": "PostgreSQL",
            "rationale": "PostgreSQL offers better JSON support because of its native JSONB type",
            "confidence": 0.8,
        }
        result = calibrate_confidence(decision)
        # Should get bonus for options >= 2, detailed rationale, context
        assert result > 0.8

    def test_calibrate_penalizes_missing_fields(self):
        """Should penalize for missing required fields."""
        decision = {
            "trigger": "",
            "decision": "Use PostgreSQL",
            "rationale": "",
            "confidence": 0.8,
        }
        result = calibrate_confidence(decision)
        # Should get penalty for missing trigger and rationale
        assert result < 0.8

    def test_calibrate_bonus_for_quality_phrases(self):
        """Should give bonus for quality reasoning phrases."""
        decision = {
            "trigger": "Database selection",
            "decision": "PostgreSQL",
            "rationale": "Because PostgreSQL offers ACID compliance due to its mature transaction support",
            "confidence": 0.8,
        }
        result = calibrate_confidence(decision)
        # Should get bonus for "because" and "due to"
        assert result > 0.8

    def test_calibrate_minimum_confidence(self):
        """Should enforce minimum confidence of 0.1."""
        decision = {
            "trigger": "",
            "decision": "",
            "rationale": "",
            "confidence": 0.1,
        }
        result = calibrate_confidence(decision)
        # Even with all penalties, should not go below 0.1
        assert result >= 0.1

    def test_calibrate_maximum_confidence(self):
        """Should enforce maximum confidence of 1.0."""
        decision = {
            "trigger": "Complex trigger",
            "context": "Very detailed context with background information",
            "options": ["A", "B", "C", "D", "E"],
            "decision": "Selected option A",
            "rationale": "Because option A is better due to performance, compared to others, "
            "considering the trade-off between cost and benefit",
            "confidence": 1.0,
        }
        result = calibrate_confidence(decision)
        assert result <= 1.0


# ============================================================================
# Apply Decision Defaults Tests
# ============================================================================


class TestApplyDecisionDefaults:
    """Test default value application for incomplete decisions."""

    def test_apply_defaults_for_missing_fields(self):
        """Should apply defaults for missing fields."""
        decision = {"decision": "Use PostgreSQL"}
        result = apply_decision_defaults(decision)

        assert result["confidence"] == 0.5
        assert result["context"] == ""
        assert result["rationale"] == ""
        assert result["options"] == []
        assert result["trigger"] == "Unknown trigger"
        assert result["decision"] == "Use PostgreSQL"

    def test_preserves_existing_values(self):
        """Should not override existing values."""
        decision = {
            "trigger": "Database choice",
            "confidence": 0.9,
            "context": "Web app",
            "decision": "PostgreSQL",
        }
        result = apply_decision_defaults(decision)

        assert result["trigger"] == "Database choice"
        assert result["confidence"] == 0.9
        assert result["context"] == "Web app"

    def test_handles_none_values(self):
        """Should replace None values with defaults."""
        decision = {
            "trigger": None,
            "confidence": None,
            "decision": "PostgreSQL",
        }
        result = apply_decision_defaults(decision)

        assert result["trigger"] == "Unknown trigger"
        assert result["confidence"] == 0.5

    def test_handles_empty_string_values(self):
        """Should replace empty strings with defaults."""
        decision = {
            "trigger": "   ",
            "decision": "PostgreSQL",
        }
        result = apply_decision_defaults(decision)

        assert result["trigger"] == "Unknown trigger"

    def test_preserves_extra_fields(self):
        """Should preserve fields not in defaults."""
        decision = {
            "decision": "PostgreSQL",
            "custom_field": "custom_value",
            "another_field": 123,
        }
        result = apply_decision_defaults(decision)

        assert result["custom_field"] == "custom_value"
        assert result["another_field"] == 123


# ============================================================================
# Decision Extraction Tests
# ============================================================================


class TestDecisionExtraction:
    """Test decision extraction from conversations."""

    @pytest.mark.asyncio
    async def test_extract_single_decision(self, extractor_with_mocks, mock_llm):
        """Should extract a single decision from conversation."""
        unique_id = str(uuid4())
        conversation = create_unique_conversation(unique_id)

        mock_llm.set_json_response(
            unique_id,
            [
                {
                    "trigger": "Need to choose a database",
                    "context": "Building a web application",
                    "options": ["PostgreSQL", "MongoDB"],
                    "decision": "Use PostgreSQL",
                    "rationale": "Better for relational data",
                    "confidence": 0.9,
                }
            ],
        )

        decisions = await extractor_with_mocks.extract_decisions(
            conversation, bypass_cache=True
        )

        assert len(decisions) == 1
        assert decisions[0].trigger == "Need to choose a database"
        assert decisions[0].decision == "Use PostgreSQL"

    @pytest.mark.asyncio
    async def test_extract_multiple_decisions(self, extractor_with_mocks, mock_llm):
        """Should extract multiple decisions from conversation."""
        unique_id = str(uuid4())
        conversation = create_unique_conversation(unique_id)

        mock_llm.set_json_response(
            unique_id,
            [
                {
                    "trigger": "Database choice",
                    "context": "Context A",
                    "options": ["PostgreSQL", "MongoDB"],
                    "decision": "PostgreSQL",
                    "rationale": "Rationale A",
                    "confidence": 0.9,
                },
                {
                    "trigger": "Framework choice",
                    "context": "Context B",
                    "options": ["FastAPI", "Django"],
                    "decision": "FastAPI",
                    "rationale": "Rationale B",
                    "confidence": 0.85,
                },
            ],
        )

        decisions = await extractor_with_mocks.extract_decisions(
            conversation, bypass_cache=True
        )

        assert len(decisions) == 2
        assert decisions[0].decision == "PostgreSQL"
        assert decisions[1].decision == "FastAPI"

    @pytest.mark.asyncio
    async def test_extract_no_decisions(self, extractor_with_mocks, mock_llm):
        """Should return empty list when no decisions found."""
        unique_id = str(uuid4())
        conversation = create_unique_conversation(unique_id)

        mock_llm.set_json_response(unique_id, [])

        decisions = await extractor_with_mocks.extract_decisions(
            conversation, bypass_cache=True
        )

        assert len(decisions) == 0

    @pytest.mark.asyncio
    async def test_extract_handles_invalid_json(self, extractor_with_mocks, mock_llm):
        """Should return empty list for invalid JSON response."""
        unique_id = str(uuid4())
        conversation = create_unique_conversation(unique_id)

        mock_llm.set_response(unique_id, "This is not valid JSON at all")

        decisions = await extractor_with_mocks.extract_decisions(
            conversation, bypass_cache=True
        )

        assert len(decisions) == 0

    @pytest.mark.asyncio
    async def test_extract_handles_llm_error(self, extractor_with_mocks, mock_llm):
        """Should return empty list on LLM error."""
        unique_id = str(uuid4())
        conversation = create_unique_conversation(unique_id)

        extractor_with_mocks.llm.generate = AsyncMock(
            side_effect=Exception("API Error")
        )

        decisions = await extractor_with_mocks.extract_decisions(
            conversation, bypass_cache=True
        )

        assert len(decisions) == 0

    @pytest.mark.asyncio
    async def test_extract_handles_timeout(self, extractor_with_mocks, mock_llm):
        """Should return empty list on timeout."""
        unique_id = str(uuid4())
        conversation = create_unique_conversation(unique_id)

        extractor_with_mocks.llm.generate = AsyncMock(
            side_effect=TimeoutError("Request timed out")
        )

        decisions = await extractor_with_mocks.extract_decisions(
            conversation, bypass_cache=True
        )

        assert len(decisions) == 0

    @pytest.mark.asyncio
    async def test_extract_handles_connection_error(
        self, extractor_with_mocks, mock_llm
    ):
        """Should return empty list on connection error."""
        unique_id = str(uuid4())
        conversation = create_unique_conversation(unique_id)

        extractor_with_mocks.llm.generate = AsyncMock(
            side_effect=ConnectionError("Connection failed")
        )

        decisions = await extractor_with_mocks.extract_decisions(
            conversation, bypass_cache=True
        )

        assert len(decisions) == 0

    @pytest.mark.asyncio
    async def test_extract_filters_empty_decisions(
        self, extractor_with_mocks, mock_llm
    ):
        """Should filter out decisions with empty decision field."""
        unique_id = str(uuid4())
        conversation = create_unique_conversation(unique_id)

        mock_llm.set_json_response(
            unique_id,
            [
                {
                    "trigger": "Database choice",
                    "context": "Context",
                    "options": ["A", "B"],
                    "decision": "A",
                    "rationale": "Rationale",
                    "confidence": 0.9,
                },
                {
                    "trigger": "Another choice",
                    "context": "Context",
                    "options": [],
                    "decision": "",  # Empty - should be filtered
                    "rationale": "",
                    "confidence": 0.5,
                },
            ],
        )

        decisions = await extractor_with_mocks.extract_decisions(
            conversation, bypass_cache=True
        )

        assert len(decisions) == 1

    @pytest.mark.asyncio
    async def test_extract_with_specialized_prompt(
        self, extractor_with_mocks, mock_llm
    ):
        """Should use specialized prompt for specific decision types."""
        unique_id = str(uuid4())
        conversation = create_unique_conversation(unique_id)

        mock_llm.set_json_response(
            "architecture",
            [
                {
                    "trigger": "Architecture decision",
                    "context": "Scalability needs",
                    "options": ["Monolith", "Microservices"],
                    "decision": "Microservices",
                    "rationale": "Better for scaling",
                    "confidence": 0.85,
                    "decision_type": "architecture",
                }
            ],
        )

        _decisions = await extractor_with_mocks.extract_decisions(
            conversation,
            decision_type=DecisionType.ARCHITECTURE,
            bypass_cache=True,
        )

        # Verify the specialized prompt was used
        last_call = mock_llm.get_last_call()
        assert "ARCHITECTURE" in last_call["prompt"].upper()


# ============================================================================
# Entity Extraction Tests
# ============================================================================


class TestEntityExtraction:
    """Test entity extraction from text."""

    @pytest.mark.asyncio
    async def test_extract_technology_entities(self, extractor_with_mocks, mock_llm):
        """Should extract technology entities."""
        unique_text = (
            f"We chose PostgreSQL for persistence and Redis for caching {uuid4()}"
        )

        mock_llm.set_json_response(
            "postgresql",
            {
                "entities": [
                    {"name": "PostgreSQL", "type": "technology", "confidence": 0.95},
                    {"name": "Redis", "type": "technology", "confidence": 0.9},
                ],
                "reasoning": "Both are database technologies",
            },
        )

        entities = await extractor_with_mocks.extract_entities(
            unique_text, bypass_cache=True
        )

        assert len(entities) == 2
        assert entities[0]["name"] == "PostgreSQL"
        assert entities[0]["type"] == "technology"

    @pytest.mark.asyncio
    async def test_extract_concept_entities(self, extractor_with_mocks, mock_llm):
        """Should extract concept entities."""
        unique_text = (
            f"Using microservices architecture with REST API communication {uuid4()}"
        )

        mock_llm.set_json_response(
            "microservices",
            {
                "entities": [
                    {"name": "microservices", "type": "concept", "confidence": 0.85},
                    {"name": "REST API", "type": "concept", "confidence": 0.9},
                ],
                "reasoning": "Architectural concepts",
            },
        )

        entities = await extractor_with_mocks.extract_entities(
            unique_text, bypass_cache=True
        )

        assert len(entities) == 2
        assert any(e["type"] == "concept" for e in entities)

    @pytest.mark.asyncio
    async def test_extract_pattern_entities(self, extractor_with_mocks, mock_llm):
        """Should extract pattern entities."""
        unique_text = f"Implementing the repository pattern for data access {uuid4()}"

        mock_llm.set_json_response(
            "repository pattern",
            {
                "entities": [
                    {
                        "name": "repository pattern",
                        "type": "pattern",
                        "confidence": 0.9,
                    },
                ],
                "reasoning": "Design pattern for data access",
            },
        )

        entities = await extractor_with_mocks.extract_entities(
            unique_text, bypass_cache=True
        )

        assert len(entities) == 1
        assert entities[0]["type"] == "pattern"

    @pytest.mark.asyncio
    async def test_extract_no_entities(self, extractor_with_mocks, mock_llm):
        """Should return empty list for text with no entities."""
        unique_text = f"Just a general conversation without technical content {uuid4()}"

        mock_llm.set_json_response(
            unique_text[:20],
            {
                "entities": [],
                "reasoning": "No technical entities found",
            },
        )

        entities = await extractor_with_mocks.extract_entities(
            unique_text, bypass_cache=True
        )

        assert len(entities) == 0

    @pytest.mark.asyncio
    async def test_extract_handles_malformed_response(
        self, extractor_with_mocks, mock_llm
    ):
        """Should return empty list for malformed LLM response."""
        unique_text = f"Some technical text {uuid4()}"

        mock_llm.set_response(unique_text[:10], "Invalid response without JSON")

        entities = await extractor_with_mocks.extract_entities(
            unique_text, bypass_cache=True
        )

        assert len(entities) == 0

    @pytest.mark.asyncio
    async def test_extract_entities_with_bypass_cache(
        self, extractor_with_mocks, mock_llm
    ):
        """Should bypass cache when requested."""
        unique_text = f"Using Python for development {uuid4()}"

        mock_llm.set_json_response(
            "python",
            {
                "entities": [
                    {"name": "Python", "type": "technology", "confidence": 0.9}
                ],
                "reasoning": "Programming language",
            },
        )

        entities = await extractor_with_mocks.extract_entities(
            unique_text, bypass_cache=True
        )

        assert len(entities) == 1


# ============================================================================
# Entity Relationship Extraction Tests
# ============================================================================


class TestEntityRelationshipExtraction:
    """Test extraction of relationships between entities."""

    @pytest.mark.asyncio
    async def test_extract_alternative_relationship(
        self, extractor_with_mocks, mock_llm
    ):
        """Should extract ALTERNATIVE_TO relationship."""
        mock_llm.set_json_response(
            "identify",
            {
                "relationships": [
                    {
                        "from": "PostgreSQL",
                        "to": "MongoDB",
                        "type": "ALTERNATIVE_TO",
                        "confidence": 0.9,
                    }
                ],
                "reasoning": "Both are databases that can be used instead of each other",
            },
        )

        entities = [
            {"name": "PostgreSQL", "type": "technology"},
            {"name": "MongoDB", "type": "technology"},
        ]

        relationships = await extractor_with_mocks.extract_entity_relationships(
            entities,
            context=f"Choosing between PostgreSQL and MongoDB {uuid4()}",
            bypass_cache=True,
        )

        assert len(relationships) == 1
        assert relationships[0]["type"] == "ALTERNATIVE_TO"

    @pytest.mark.asyncio
    async def test_extract_depends_on_relationship(
        self, extractor_with_mocks, mock_llm
    ):
        """Should extract DEPENDS_ON relationship."""
        mock_llm.set_json_response(
            "identify",
            {
                "relationships": [
                    {
                        "from": "Next.js",
                        "to": "React",
                        "type": "DEPENDS_ON",
                        "confidence": 0.95,
                    }
                ],
                "reasoning": "Next.js is built on React",
            },
        )

        entities = [
            {"name": "Next.js", "type": "technology"},
            {"name": "React", "type": "technology"},
        ]

        relationships = await extractor_with_mocks.extract_entity_relationships(
            entities,
            context=f"Building frontend with Next.js {uuid4()}",
            bypass_cache=True,
        )

        assert len(relationships) == 1
        assert relationships[0]["type"] == "DEPENDS_ON"

    @pytest.mark.asyncio
    async def test_extract_multiple_relationships(self, extractor_with_mocks, mock_llm):
        """Should extract multiple relationships."""
        mock_llm.set_json_response(
            "identify",
            {
                "relationships": [
                    {
                        "from": "PostgreSQL",
                        "to": "database",
                        "type": "IS_A",
                        "confidence": 0.95,
                    },
                    {
                        "from": "Redis",
                        "to": "caching",
                        "type": "PART_OF",
                        "confidence": 0.9,
                    },
                    {
                        "from": "Redis",
                        "to": "database",
                        "type": "IS_A",
                        "confidence": 0.85,
                    },
                ],
                "reasoning": "Both are databases with different purposes",
            },
        )

        entities = [
            {"name": "PostgreSQL", "type": "technology"},
            {"name": "Redis", "type": "technology"},
            {"name": "database", "type": "concept"},
            {"name": "caching", "type": "concept"},
        ]

        relationships = await extractor_with_mocks.extract_entity_relationships(
            entities, context=f"Database architecture {uuid4()}", bypass_cache=True
        )

        assert len(relationships) == 3

    @pytest.mark.asyncio
    async def test_extract_no_relationships_for_single_entity(
        self, extractor_with_mocks
    ):
        """Should return empty list for single entity."""
        entities = [{"name": "PostgreSQL", "type": "technology"}]

        relationships = await extractor_with_mocks.extract_entity_relationships(
            entities, context="Single entity", bypass_cache=True
        )

        assert len(relationships) == 0

    @pytest.mark.asyncio
    async def test_validates_relationship_types(self, extractor_with_mocks, mock_llm):
        """Should validate and filter invalid relationship types."""
        mock_llm.set_json_response(
            "identify",
            {
                "relationships": [
                    {"from": "A", "to": "B", "type": "INVALID_TYPE", "confidence": 0.9},
                    {"from": "C", "to": "D", "type": "RELATED_TO", "confidence": 0.8},
                ],
                "reasoning": "Test relationships",
            },
        )

        entities = [
            {"name": "A", "type": "technology"},
            {"name": "B", "type": "technology"},
            {"name": "C", "type": "technology"},
            {"name": "D", "type": "technology"},
        ]

        relationships = await extractor_with_mocks.extract_entity_relationships(
            entities, context=f"Test {uuid4()}", bypass_cache=True
        )

        # Invalid type should be converted to RELATED_TO with lower confidence
        assert all(
            r["type"]
            in ["RELATED_TO", "IS_A", "PART_OF", "DEPENDS_ON", "ALTERNATIVE_TO"]
            for r in relationships
        )


# ============================================================================
# Decision Relationship Extraction Tests
# ============================================================================


class TestDecisionRelationshipExtraction:
    """Test extraction of relationships between decisions."""

    @pytest.mark.asyncio
    async def test_detect_supersedes_relationship(self, extractor_with_mocks, mock_llm):
        """Should detect SUPERSEDES relationship."""
        mock_llm.set_json_response(
            "analyze",
            {
                "relationship": "SUPERSEDES",
                "confidence": 0.9,
                "reasoning": "New decision explicitly replaces the old one",
            },
        )

        decision_a = {
            "created_at": "2024-01-01",
            "trigger": "Initial database choice",
            "decision": "Use PostgreSQL",
            "rationale": "Good for relational data",
        }
        decision_b = {
            "created_at": "2024-02-01",
            "trigger": "Reconsidering database",
            "decision": "Switch to MongoDB",
            "rationale": "Need document flexibility",
        }

        result = await extractor_with_mocks.extract_decision_relationship(
            decision_a, decision_b
        )

        assert result is not None
        assert result["type"] == "SUPERSEDES"
        assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_detect_contradicts_relationship(
        self, extractor_with_mocks, mock_llm
    ):
        """Should detect CONTRADICTS relationship."""
        mock_llm.set_json_response(
            "analyze",
            {
                "relationship": "CONTRADICTS",
                "confidence": 0.85,
                "reasoning": "Decisions recommend conflicting approaches",
            },
        )

        decision_a = {
            "created_at": "2024-01-01",
            "trigger": "Authentication approach",
            "decision": "Use JWT tokens",
            "rationale": "Stateless authentication",
        }
        decision_b = {
            "created_at": "2024-01-05",
            "trigger": "Authentication approach",
            "decision": "Use session cookies",
            "rationale": "Stateful is more secure",
        }

        result = await extractor_with_mocks.extract_decision_relationship(
            decision_a, decision_b
        )

        assert result is not None
        assert result["type"] == "CONTRADICTS"

    @pytest.mark.asyncio
    async def test_detect_no_relationship(self, extractor_with_mocks, mock_llm):
        """Should return None when no significant relationship."""
        mock_llm.set_json_response(
            "analyze",
            {
                "relationship": None,
                "confidence": 0.0,
                "reasoning": "Decisions are about different topics",
            },
        )

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

        result = await extractor_with_mocks.extract_decision_relationship(
            decision_a, decision_b
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_decision_relationship_error(
        self, extractor_with_mocks, mock_llm
    ):
        """Should return None on error."""
        extractor_with_mocks.llm.generate = AsyncMock(
            side_effect=Exception("API Error")
        )

        decision_a = {
            "created_at": "2024-01-01",
            "trigger": "A",
            "decision": "A",
            "rationale": "A",
        }
        decision_b = {
            "created_at": "2024-01-02",
            "trigger": "B",
            "decision": "B",
            "rationale": "B",
        }

        result = await extractor_with_mocks.extract_decision_relationship(
            decision_a, decision_b
        )

        assert result is None


# ============================================================================
# LLM Response Cache Tests
# ============================================================================


class TestLLMResponseCache:
    """Test LLM response caching functionality."""

    @pytest.mark.asyncio
    async def test_cache_generates_correct_key(self):
        """Should generate deterministic cache keys."""
        with patch("services.extractor.get_settings") as mock_settings:
            mock_settings.return_value.llm_extraction_prompt_version = "v1"
            cache = LLMResponseCache()

            # Same text and type should produce same key
            key1 = cache._get_cache_key("test text", "decisions")
            key2 = cache._get_cache_key("test text", "decisions")
            assert key1 == key2

            # Different text should produce different key
            key3 = cache._get_cache_key("different text", "decisions")
            assert key1 != key3

            # Different type should produce different key
            key4 = cache._get_cache_key("test text", "entities")
            assert key1 != key4

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self, mock_redis):
        """Should return None on cache miss."""
        with patch("services.extractor.get_settings") as mock_settings:
            mock_settings.return_value.llm_cache_enabled = True
            mock_settings.return_value.redis_url = "redis://localhost:6379"
            mock_settings.return_value.llm_extraction_prompt_version = "v1"

            cache = LLMResponseCache()
            cache._redis = mock_redis

            result = await cache.get("nonexistent", "decisions")

            # With mock returning None, should return None
            assert result is None

    @pytest.mark.asyncio
    async def test_cache_disabled_returns_none(self):
        """Should return None when cache is disabled."""
        with patch("services.extractor.get_settings") as mock_settings:
            mock_settings.return_value.llm_cache_enabled = False

            cache = LLMResponseCache()
            result = await cache.get("test", "decisions")

            assert result is None


# ============================================================================
# Conversation Processing Tests
# ============================================================================


class TestConversationProcessing:
    """Test conversation object handling."""

    def test_conversation_get_full_text(self, sample_conversation):
        """Should return full conversation as text."""
        full_text = sample_conversation.get_full_text()

        assert "user:" in full_text.lower()
        assert "assistant:" in full_text.lower()
        assert "database" in full_text.lower()

    def test_conversation_get_preview(self, sample_conversation):
        """Should return truncated preview."""
        preview = sample_conversation.get_preview(max_chars=50)

        assert len(preview) <= 53  # 50 + "..."
        assert preview.endswith("...")

    def test_conversation_get_preview_short_text(self):
        """Should return full text if shorter than max_chars."""
        short_conv = Conversation(
            messages=[{"role": "user", "content": "Hi"}],
            file_path="/test",
            project_name="test",
        )

        preview = short_conv.get_preview(max_chars=100)

        assert not preview.endswith("...")


# ============================================================================
# Factory Function Tests
# ============================================================================


class TestGetExtractor:
    """Test the factory function."""

    def test_creates_singleton_instance(self):
        """Should return the same instance on multiple calls."""
        with (
            patch("services.extractor.get_llm_client"),
            patch("services.extractor.get_embedding_service"),
            patch("services.extractor.get_settings") as mock_settings,
        ):
            mock_settings.return_value.similarity_threshold = 0.7
            mock_settings.return_value.high_confidence_similarity_threshold = 0.85

            extractor1 = get_extractor()
            extractor2 = get_extractor()

            assert extractor1 is extractor2

    def test_creates_extractor_with_dependencies(self):
        """Should create extractor with LLM and embedding service."""
        with (
            patch("services.extractor.get_llm_client") as _mock_llm,
            patch("services.extractor.get_embedding_service") as _mock_embed,
            patch("services.extractor.get_settings") as mock_settings,
        ):
            mock_settings.return_value.similarity_threshold = 0.7
            mock_settings.return_value.high_confidence_similarity_threshold = 0.85

            # Reset singleton
            import services.extractor

            services.extractor._extractor = None

            extractor = get_extractor()

            assert isinstance(extractor, DecisionExtractor)


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_extract_with_unicode_text(self, extractor_with_mocks, mock_llm):
        """Should handle unicode text correctly."""
        unique_text = f"使用 PostgreSQL 数据库 emoji:  {uuid4()}"

        mock_llm.set_json_response(
            "postgresql",
            {
                "entities": [
                    {"name": "PostgreSQL", "type": "technology", "confidence": 0.9}
                ],
                "reasoning": "Database",
            },
        )

        entities = await extractor_with_mocks.extract_entities(
            unique_text, bypass_cache=True
        )

        assert len(entities) >= 0  # Should not raise error

    @pytest.mark.asyncio
    async def test_extract_with_empty_text(self, extractor_with_mocks, mock_llm):
        """Should handle empty text."""
        mock_llm.set_json_response("", {"entities": [], "reasoning": "Empty"})

        entities = await extractor_with_mocks.extract_entities("", bypass_cache=True)

        assert len(entities) == 0

    @pytest.mark.asyncio
    async def test_extract_with_very_long_text(self, extractor_with_mocks, mock_llm):
        """Should handle very long text."""
        long_text = f"PostgreSQL {uuid4()} " * 1000  # Very long text

        mock_llm.set_json_response(
            "postgresql",
            {
                "entities": [
                    {"name": "PostgreSQL", "type": "technology", "confidence": 0.9}
                ],
                "reasoning": "Found in long text",
            },
        )

        entities = await extractor_with_mocks.extract_entities(
            long_text, bypass_cache=True
        )

        # Should not raise error
        assert isinstance(entities, list)

    @pytest.mark.asyncio
    async def test_extract_with_markdown_json_response(
        self, extractor_with_mocks, mock_llm
    ):
        """Should parse JSON wrapped in markdown code blocks."""
        unique_text = f"Using Python {uuid4()}"

        mock_llm.set_response(
            "python",
            """```json
{
    "entities": [{"name": "Python", "type": "technology", "confidence": 0.9}],
    "reasoning": "Programming language"
}
```""",
        )

        entities = await extractor_with_mocks.extract_entities(
            unique_text, bypass_cache=True
        )

        assert len(entities) == 1
        assert entities[0]["name"] == "Python"


# ============================================================================
# Run tests
# ============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
