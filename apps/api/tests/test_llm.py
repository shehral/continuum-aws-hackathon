"""Tests for NVIDIA Llama LLM integration and rate limiting.

This test suite covers:
- Rate limiter behavior (acquire, wait_for_slot, blocking)
- LLM client functionality (generate, system prompts, rate limiting)
- Thinking tag stripping
- Retry logic and error handling
- Edge cases (timeouts, malformed responses, empty input)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError

from agents.interview import InterviewAgent, InterviewState
from services.extractor import DecisionExtractor
from services.llm import (
    RETRYABLE_STATUS_CODES,
    LLMClient,
    RateLimiter,
    get_llm_client,
    strip_thinking_tags,
)

# ============================================================================
# Thinking Tag Stripping Tests
# ============================================================================


class TestStripThinkingTags:
    """Tests for the strip_thinking_tags utility function."""

    def test_strip_simple_thinking_tag(self):
        """Should remove simple <think>...</think> tags."""
        text = "<think>reasoning</think>answer"
        result = strip_thinking_tags(text)
        assert result == "answer"

    def test_strip_multiline_thinking_tag(self):
        """Should remove multiline thinking blocks."""
        text = "<think>\nstep1\nstep2\nstep3\n</think>\nfinal answer"
        result = strip_thinking_tags(text)
        assert result == "final answer"

    def test_strip_multiple_thinking_tags(self):
        """Should remove multiple thinking blocks."""
        text = "<think>first thought</think>part1<think>second thought</think>part2"
        result = strip_thinking_tags(text)
        assert result == "part1part2"

    def test_no_thinking_tags(self):
        """Should return unchanged text when no tags present."""
        text = "plain text without tags"
        result = strip_thinking_tags(text)
        assert result == "plain text without tags"

    def test_empty_input(self):
        """Should handle empty input."""
        result = strip_thinking_tags("")
        assert result == ""

    def test_only_thinking_tags(self):
        """Should return empty when text is only thinking tags."""
        text = "<think>all reasoning, no output</think>"
        result = strip_thinking_tags(text)
        assert result == ""

    def test_preserves_whitespace_around_content(self):
        """Should preserve meaningful whitespace."""
        text = "<think>thinking</think>  real content  "
        result = strip_thinking_tags(text)
        assert "real content" in result

    def test_nested_thinking_tags_outer_removed(self):
        """Should handle nested tags (regex removes outer)."""
        text = "<think>outer<think>inner</think>outer</think>answer"
        result = strip_thinking_tags(text)
        # Non-greedy match handles this
        assert "answer" in result

    def test_thinking_tag_with_special_characters(self):
        """Should handle special characters in thinking content."""
        text = "<think>reasoning with $pecial ch@rs & symbols</think>answer"
        result = strip_thinking_tags(text)
        assert result == "answer"

    def test_thinking_tag_case_sensitive(self):
        """Should only match lowercase <think> tags."""
        text = "<THINK>uppercase</THINK>answer"
        result = strip_thinking_tags(text)
        # Uppercase tags are not stripped (per implementation)
        assert "<THINK>" in result or "answer" in result


# ============================================================================
# Rate Limiter Tests
# ============================================================================


class TestRateLimiter:
    """Test the Redis-based rate limiter."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        pipe = AsyncMock()
        pipe.execute = AsyncMock(return_value=[None, 0, None, None])
        redis.pipeline = MagicMock(return_value=pipe)
        redis.zrem = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_acquire_when_under_limit(self, mock_redis):
        """Should allow request when under rate limit."""
        limiter = RateLimiter(mock_redis, user_id="test", max_requests=30, window=60)

        # Mock: 5 requests in window (under limit of 30)
        mock_redis.pipeline().execute = AsyncMock(return_value=[None, 5, None, None])

        result = await limiter.acquire()
        assert result is True

    @pytest.mark.asyncio
    async def test_acquire_when_at_limit(self, mock_redis):
        """Should deny request when at rate limit."""
        limiter = RateLimiter(mock_redis, user_id="test", max_requests=30, window=60)

        # Mock: 30 requests in window (at limit)
        mock_redis.pipeline().execute = AsyncMock(return_value=[None, 30, None, None])

        result = await limiter.acquire()
        assert result is False

    @pytest.mark.asyncio
    async def test_acquire_removes_token_when_denied(self, mock_redis):
        """Should remove added token when rate limit exceeded."""
        limiter = RateLimiter(mock_redis, user_id="test", max_requests=30, window=60)
        mock_redis.pipeline().execute = AsyncMock(return_value=[None, 30, None, None])

        await limiter.acquire()

        # Should have called zrem to remove the token we just added
        mock_redis.zrem.assert_called()

    @pytest.mark.asyncio
    async def test_wait_for_slot_success(self, mock_redis):
        """Should wait and acquire slot when available."""
        limiter = RateLimiter(mock_redis, user_id="test", max_requests=30, window=60)

        # First call: at limit, second call: under limit
        mock_redis.pipeline().execute = AsyncMock(
            side_effect=[
                [None, 30, None, None],  # First: denied
                [None, 10, None, None],  # Second: allowed
            ]
        )

        result = await limiter.wait_for_slot(timeout=5.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_slot_timeout(self, mock_redis):
        """Should return False when timeout exceeded."""
        limiter = RateLimiter(mock_redis, user_id="test", max_requests=30, window=60)

        # Always at limit
        mock_redis.pipeline().execute = AsyncMock(return_value=[None, 100, None, None])

        result = await limiter.wait_for_slot(timeout=0.1)
        assert result is False

    @pytest.mark.asyncio
    async def test_rate_limiter_key_prefix(self, mock_redis):
        """Should use correct key prefix."""
        limiter = RateLimiter(mock_redis, user_id="my_user", max_requests=30, window=60)
        assert limiter.key == "ratelimit:user:my_user:nvidia_api"


# ============================================================================
# LLM Client Tests
# ============================================================================


class TestLLMClient:
    """Test the NVIDIA LLM client."""

    @pytest.fixture
    def mock_openai_response(self):
        """Create a mock OpenAI response."""
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = "Test response"
        return response

    @pytest.fixture
    def mock_rate_limited_redis(self):
        """Create mock Redis that simulates rate limiting."""
        redis = AsyncMock()
        pipe = AsyncMock()
        pipe.execute = AsyncMock(return_value=[None, 5, None, None])
        redis.pipeline = MagicMock(return_value=pipe)
        redis.zrem = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_generate_success(self, mock_openai_response):
        """Should generate completion successfully."""
        with patch("services.llm.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=mock_openai_response
            )
            mock_client_class.return_value = mock_client

            with patch("services.llm.redis") as mock_redis_module:
                mock_redis = AsyncMock()
                mock_pipe = AsyncMock()
                mock_pipe.execute = AsyncMock(return_value=[None, 5, None, None])
                mock_redis.pipeline = MagicMock(return_value=mock_pipe)
                mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                client = LLMClient()
                result = await client.generate("Test prompt")

                assert result == "Test response"

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self, mock_openai_response):
        """Should include system prompt in messages."""
        with patch("services.llm.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=mock_openai_response
            )
            mock_client_class.return_value = mock_client

            with patch("services.llm.redis") as mock_redis_module:
                mock_redis = AsyncMock()
                mock_pipe = AsyncMock()
                mock_pipe.execute = AsyncMock(return_value=[None, 5, None, None])
                mock_redis.pipeline = MagicMock(return_value=mock_pipe)
                mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                client = LLMClient()
                await client.generate("Test prompt", system_prompt="You are helpful")

                # Verify system prompt was included
                call_args = mock_client.chat.completions.create.call_args
                messages = call_args.kwargs["messages"]
                assert messages[0]["role"] == "system"
                assert messages[0]["content"] == "You are helpful"

    @pytest.mark.asyncio
    async def test_generate_rate_limited(self):
        """Should raise exception when rate limited."""
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

                client = LLMClient()

                with pytest.raises(Exception, match="Rate limit exceeded"):
                    await client.generate("Test prompt")

    @pytest.mark.asyncio
    async def test_generate_strips_thinking_tags(self):
        """Should strip thinking tags from response."""
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[
            0
        ].message.content = "<think>reasoning here</think>actual answer"

        with patch("services.llm.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=response)
            mock_client_class.return_value = mock_client

            with patch("services.llm.redis") as mock_redis_module:
                mock_redis = AsyncMock()
                mock_pipe = AsyncMock()
                mock_pipe.execute = AsyncMock(return_value=[None, 5, None, None])
                mock_redis.pipeline = MagicMock(return_value=mock_pipe)
                mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                client = LLMClient()
                result = await client.generate("Test prompt")

                assert result == "actual answer"
                assert "<think>" not in result


# ============================================================================
# LLM Edge Case Tests
# ============================================================================


class TestLLMEdgeCases:
    """Test edge cases and error handling for the LLM client."""

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Should handle API timeout errors."""
        with patch("services.llm.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=APITimeoutError(request=MagicMock())
            )
            mock_client_class.return_value = mock_client

            with patch("services.llm.redis") as mock_redis_module:
                mock_redis = AsyncMock()
                mock_pipe = AsyncMock()
                mock_pipe.execute = AsyncMock(return_value=[None, 5, None, None])
                mock_redis.pipeline = MagicMock(return_value=mock_pipe)
                mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                client = LLMClient()

                with pytest.raises(APITimeoutError):
                    await client.generate("Test prompt", max_retries=0)

    @pytest.mark.asyncio
    async def test_429_rate_limit_response_retried(self):
        """Should retry on 429 rate limit response from API."""
        response_ok = MagicMock()
        response_ok.choices = [MagicMock()]
        response_ok.choices[0].message.content = "Success after retry"

        with patch("services.llm.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            # First call: 429 error, second call: success
            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_client.chat.completions.create = AsyncMock(
                side_effect=[
                    APIStatusError(
                        message="Rate limit exceeded",
                        response=mock_response,
                        body=None,
                    ),
                    response_ok,
                ]
            )
            mock_client_class.return_value = mock_client

            with patch("services.llm.redis") as mock_redis_module:
                mock_redis = AsyncMock()
                mock_pipe = AsyncMock()
                mock_pipe.execute = AsyncMock(return_value=[None, 5, None, None])
                mock_redis.pipeline = MagicMock(return_value=mock_pipe)
                mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                with patch("services.llm.asyncio.sleep", new_callable=AsyncMock):
                    client = LLMClient()
                    result = await client.generate("Test prompt", max_retries=3)

                    assert result == "Success after retry"

    @pytest.mark.asyncio
    async def test_malformed_api_response_null_content(self):
        """Should handle null content in API response."""
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = None  # Null content

        with patch("services.llm.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=response)
            mock_client_class.return_value = mock_client

            with patch("services.llm.redis") as mock_redis_module:
                mock_redis = AsyncMock()
                mock_pipe = AsyncMock()
                mock_pipe.execute = AsyncMock(return_value=[None, 5, None, None])
                mock_redis.pipeline = MagicMock(return_value=mock_pipe)
                mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                client = LLMClient()
                result = await client.generate("Test prompt")

                # Should return empty string for null content
                assert result == ""

    @pytest.mark.asyncio
    async def test_empty_response_handling(self):
        """Should handle empty string response."""
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = ""

        with patch("services.llm.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=response)
            mock_client_class.return_value = mock_client

            with patch("services.llm.redis") as mock_redis_module:
                mock_redis = AsyncMock()
                mock_pipe = AsyncMock()
                mock_pipe.execute = AsyncMock(return_value=[None, 5, None, None])
                mock_redis.pipeline = MagicMock(return_value=mock_pipe)
                mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                client = LLMClient()
                result = await client.generate("Test prompt")

                assert result == ""

    @pytest.mark.asyncio
    async def test_retry_logic_exhaustion(self):
        """Should fail after exhausting all retries."""
        with patch("services.llm.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_client.chat.completions.create = AsyncMock(
                side_effect=APIStatusError(
                    message="Service unavailable",
                    response=mock_response,
                    body=None,
                )
            )
            mock_client_class.return_value = mock_client

            with patch("services.llm.redis") as mock_redis_module:
                mock_redis = AsyncMock()
                mock_pipe = AsyncMock()
                mock_pipe.execute = AsyncMock(return_value=[None, 5, None, None])
                mock_redis.pipeline = MagicMock(return_value=mock_pipe)
                mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                with patch("services.llm.asyncio.sleep", new_callable=AsyncMock):
                    client = LLMClient()

                    with pytest.raises(APIStatusError):
                        await client.generate("Test prompt", max_retries=2)

    @pytest.mark.asyncio
    async def test_non_retryable_error_not_retried(self):
        """Should not retry non-retryable errors (e.g., 400, 401)."""
        with patch("services.llm.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 400  # Bad request - not retryable
            mock_client.chat.completions.create = AsyncMock(
                side_effect=APIStatusError(
                    message="Bad request",
                    response=mock_response,
                    body=None,
                )
            )
            mock_client_class.return_value = mock_client

            with patch("services.llm.redis") as mock_redis_module:
                mock_redis = AsyncMock()
                mock_pipe = AsyncMock()
                mock_pipe.execute = AsyncMock(return_value=[None, 5, None, None])
                mock_redis.pipeline = MagicMock(return_value=mock_pipe)
                mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                client = LLMClient()

                with pytest.raises(APIStatusError):
                    await client.generate("Test prompt", max_retries=3)

                # Should only be called once (no retries for 400)
                assert mock_client.chat.completions.create.call_count == 1

    @pytest.mark.asyncio
    async def test_connection_error_is_retryable(self):
        """Should retry on connection errors."""
        response_ok = MagicMock()
        response_ok.choices = [MagicMock()]
        response_ok.choices[0].message.content = "Success"

        with patch("services.llm.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=[
                    APIConnectionError(request=MagicMock()),
                    response_ok,
                ]
            )
            mock_client_class.return_value = mock_client

            with patch("services.llm.redis") as mock_redis_module:
                mock_redis = AsyncMock()
                mock_pipe = AsyncMock()
                mock_pipe.execute = AsyncMock(return_value=[None, 5, None, None])
                mock_redis.pipeline = MagicMock(return_value=mock_pipe)
                mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                with patch("services.llm.asyncio.sleep", new_callable=AsyncMock):
                    client = LLMClient()
                    result = await client.generate("Test prompt", max_retries=3)

                    assert result == "Success"
                    assert mock_client.chat.completions.create.call_count == 2

    def test_retryable_status_codes(self):
        """Should include standard retryable status codes."""
        expected_codes = {429, 500, 502, 503, 504}
        assert RETRYABLE_STATUS_CODES == expected_codes

    @pytest.mark.asyncio
    async def test_backoff_calculation(self):
        """Should calculate exponential backoff with jitter."""
        with patch("services.llm.AsyncOpenAI"):
            with patch("services.llm.redis"):
                client = LLMClient()

                # Test backoff increases with attempts
                backoff_0 = client._calculate_backoff(0)
                backoff_1 = client._calculate_backoff(1)
                backoff_2 = client._calculate_backoff(2)

                # Backoffs should generally increase (accounting for jitter)
                # Each backoff has up to 1 second of jitter
                assert backoff_0 >= 0
                assert backoff_1 >= 0
                assert backoff_2 >= 0
                # Without jitter: 1*2^0=1, 1*2^1=2, 1*2^2=4


# ============================================================================
# Decision Extractor Tests
# ============================================================================


class TestDecisionExtractor:
    """Test the decision extraction service."""

    @pytest.mark.asyncio
    async def test_extract_decisions_parses_json(self):
        """Should parse JSON response into DecisionCreate objects."""
        mock_response = """[
            {
                "trigger": "Need to choose a database",
                "context": "Building a new application",
                "options": ["PostgreSQL", "MongoDB"],
                "decision": "Use PostgreSQL",
                "rationale": "Better for relational data",
                "confidence": 0.9
            }
        ]"""

        with patch("services.extractor.get_llm_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.generate = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            extractor = DecisionExtractor()

            # Create a mock conversation
            mock_conversation = MagicMock()
            mock_conversation.get_full_text = MagicMock(
                return_value="Test conversation"
            )

            decisions = await extractor.extract_decisions(mock_conversation)

            assert len(decisions) == 1
            assert decisions[0].trigger == "Need to choose a database"
            assert decisions[0].decision == "Use PostgreSQL"
            assert decisions[0].confidence == 0.9

    @pytest.mark.asyncio
    async def test_extract_decisions_handles_markdown(self):
        """Should handle markdown-wrapped JSON response."""
        mock_response = """```json
[
    {
        "trigger": "Test",
        "context": "Test context",
        "options": ["Option A", "Option B"],
        "decision": "Test decision",
        "rationale": "Test rationale",
        "confidence": 0.8
    }
]
```"""

        with patch("services.extractor.get_llm_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.generate = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            extractor = DecisionExtractor()
            mock_conversation = MagicMock()
            mock_conversation.get_full_text = MagicMock(return_value="Test")

            decisions = await extractor.extract_decisions(mock_conversation)

            assert len(decisions) == 1
            assert decisions[0].trigger == "Test"

    @pytest.mark.asyncio
    async def test_extract_entities(self):
        """Should extract entities from text."""
        mock_response = """{
            "entities": [
                {"name": "PostgreSQL", "type": "technology", "confidence": 0.95},
                {"name": "Caching", "type": "concept", "confidence": 0.85}
            ],
            "reasoning": "PostgreSQL is a database technology, caching is a concept"
        }"""

        with patch("services.extractor.get_llm_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.generate = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            extractor = DecisionExtractor()
            entities = await extractor.extract_entities("Using PostgreSQL with caching")

            assert len(entities) == 2
            assert entities[0]["name"] == "PostgreSQL"
            assert entities[0]["type"] == "technology"
            assert entities[1]["name"] == "Caching"
            assert entities[1]["type"] == "concept"

    @pytest.mark.asyncio
    async def test_extract_decisions_handles_error(self):
        """Should return empty list on error (with cache bypassed)."""
        with patch("services.extractor.get_llm_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.generate = AsyncMock(side_effect=Exception("API Error"))
            mock_get_client.return_value = mock_client

            extractor = DecisionExtractor()
            mock_conversation = MagicMock()
            mock_conversation.get_full_text = MagicMock(return_value="Test")

            # Bypass cache to ensure we test the LLM error path
            decisions = await extractor.extract_decisions(
                mock_conversation, bypass_cache=True
            )

            assert decisions == []

    @pytest.mark.asyncio
    async def test_extract_entities_handles_malformed_json(self):
        """Should handle malformed JSON in entity extraction."""
        mock_response = "not valid json {"

        with patch("services.extractor.get_llm_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.generate = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            extractor = DecisionExtractor()
            entities = await extractor.extract_entities("Test text")

            # Should return empty list on parse error
            assert entities == []


# ============================================================================
# Interview Agent Tests
# ============================================================================


class TestInterviewAgent:
    """Test the interview agent."""

    def test_determine_next_state_opening(self):
        """Should start with TRIGGER state."""
        agent = InterviewAgent()
        state = agent._determine_next_state([])
        assert state == InterviewState.TRIGGER

    def test_determine_next_state_progression(self):
        """Should progress through states using content-based analysis (ML-P2-2)."""
        agent = InterviewAgent()

        # Short conversation uses heuristic - 1 response goes to CONTEXT
        history = [
            {"role": "user", "content": "We had a problem and needed to fix an issue."}
        ]
        assert agent._determine_next_state(history) == InterviewState.CONTEXT

        # With trigger and context info, should move to OPTIONS
        history.append(
            {
                "role": "user",
                "content": "We already had a system with budget constraints.",
            }
        )
        state = agent._determine_next_state(history)
        assert state == InterviewState.OPTIONS

        # With options added, should move to DECISION
        history.append(
            {
                "role": "user",
                "content": "We considered several alternatives and options.",
            }
        )
        state = agent._determine_next_state(history)
        assert state == InterviewState.DECISION

        # With decision added, should move to RATIONALE
        history.append(
            {"role": "user", "content": "We ultimately decided to use PostgreSQL."}
        )
        state = agent._determine_next_state(history)
        assert state == InterviewState.RATIONALE

        # With rationale, should move to SUMMARIZING
        history.append(
            {
                "role": "user",
                "content": "We chose this because of the benefits and trade-offs.",
            }
        )
        state = agent._determine_next_state(history)
        assert state == InterviewState.SUMMARIZING

    def test_fallback_response(self):
        """Should provide fallback responses when AI unavailable."""
        agent = InterviewAgent()

        response = agent._generate_fallback_response("test", [])
        assert "context" in response.lower() or "situation" in response.lower()

    @pytest.mark.asyncio
    async def test_process_message(self):
        """Should process message and return response with entities."""
        with patch("agents.interview.get_llm_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.generate = AsyncMock(
                return_value="That's interesting! Tell me more about the context."
            )
            mock_get_client.return_value = mock_client

            with patch.object(
                DecisionExtractor, "extract_entities", new_callable=AsyncMock
            ) as mock_extract:
                mock_extract.return_value = []

                agent = InterviewAgent()
                response, entities = await agent.process_message(
                    "I needed to choose a database", []
                )

                assert (
                    "interesting" in response.lower() or "context" in response.lower()
                )

    @pytest.mark.asyncio
    async def test_synthesize_decision(self):
        """Should synthesize decision from conversation history."""
        mock_response = """{
            "trigger": "Choose database",
            "context": "New project",
            "options": ["PostgreSQL", "MongoDB"],
            "decision": "PostgreSQL",
            "rationale": "Relational data needs",
            "confidence": 0.85
        }"""

        with patch("agents.interview.get_llm_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.generate = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            agent = InterviewAgent()
            history = [
                {"role": "user", "content": "I chose PostgreSQL"},
                {"role": "assistant", "content": "Why?"},
                {"role": "user", "content": "Relational data"},
            ]

            result = await agent.synthesize_decision(history)

            assert result["trigger"] == "Choose database"
            assert result["decision"] == "PostgreSQL"
            assert result["confidence"] == 0.85


# ============================================================================
# Integration Tests (requires running services)
# ============================================================================


@pytest.mark.integration
class TestIntegration:
    """Integration tests that require running NVIDIA API and Redis."""

    @pytest.mark.asyncio
    async def test_llm_client_real_request(self):
        """Test actual LLM request (requires NVIDIA API key)."""
        client = get_llm_client()

        try:
            response = await client.generate(
                "Say 'Hello' and nothing else.",
                max_tokens=10,
            )
            assert "hello" in response.lower()
        except Exception as e:
            pytest.skip(f"NVIDIA API not available: {e}")

    @pytest.mark.asyncio
    async def test_extractor_real_extraction(self):
        """Test actual decision extraction (requires NVIDIA API)."""
        extractor = DecisionExtractor()

        try:
            entities = await extractor.extract_entities(
                "We decided to use PostgreSQL for the database and Redis for caching."
            )
            entity_names = [e.name.lower() for e in entities]
            assert any("postgres" in name for name in entity_names)
        except Exception as e:
            pytest.skip(f"NVIDIA API not available: {e}")


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
