"""Tests for LLM client retry logic with exponential backoff."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError

from services.llm import RETRYABLE_STATUS_CODES, LLMClient


class TestRetryLogic:
    """Test the retry logic in LLMClient."""

    @pytest.fixture
    def mock_openai_response(self):
        """Create a mock OpenAI response."""
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = "Test response"
        return response

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client that allows requests."""
        redis = AsyncMock()
        pipe = AsyncMock()
        # Allow request (under limit)
        pipe.execute = AsyncMock(return_value=[None, 5, None, None])
        redis.pipeline = MagicMock(return_value=pipe)
        redis.zrem = AsyncMock()
        return redis

    def test_retryable_status_codes(self):
        """Should have correct retryable status codes."""
        assert 429 in RETRYABLE_STATUS_CODES  # Rate limit
        assert 500 in RETRYABLE_STATUS_CODES  # Internal server error
        assert 502 in RETRYABLE_STATUS_CODES  # Bad gateway
        assert 503 in RETRYABLE_STATUS_CODES  # Service unavailable
        assert 504 in RETRYABLE_STATUS_CODES  # Gateway timeout
        assert 400 not in RETRYABLE_STATUS_CODES  # Bad request
        assert 401 not in RETRYABLE_STATUS_CODES  # Unauthorized
        assert 404 not in RETRYABLE_STATUS_CODES  # Not found

    @pytest.mark.asyncio
    async def test_is_retryable_error_connection_errors(self):
        """Should identify connection errors as retryable."""
        with patch("services.llm.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                nvidia_api_key="test",
                nvidia_model="test",
                redis_url="redis://localhost",
                rate_limit_requests=30,
                rate_limit_window=60,
                llm_max_retries=3,
                llm_retry_base_delay=1.0,
                max_prompt_tokens=12000,
                prompt_warning_threshold=0.8,
            )
            mock_settings.return_value.get_nvidia_api_key = MagicMock(
                return_value="test"
            )

            with patch("services.llm.AsyncOpenAI"):
                client = LLMClient()

                assert client._is_retryable_error(TimeoutError())
                assert client._is_retryable_error(ConnectionError())
                assert client._is_retryable_error(
                    APIConnectionError(request=MagicMock())
                )
                assert client._is_retryable_error(APITimeoutError(request=MagicMock()))

    @pytest.mark.asyncio
    async def test_is_retryable_error_status_codes(self):
        """Should identify retryable HTTP status codes."""
        with patch("services.llm.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                nvidia_api_key="test",
                nvidia_model="test",
                redis_url="redis://localhost",
                rate_limit_requests=30,
                rate_limit_window=60,
                llm_max_retries=3,
                llm_retry_base_delay=1.0,
                max_prompt_tokens=12000,
                prompt_warning_threshold=0.8,
            )
            mock_settings.return_value.get_nvidia_api_key = MagicMock(
                return_value="test"
            )

            with patch("services.llm.AsyncOpenAI"):
                client = LLMClient()

                # Create mock API errors
                def make_api_error(status_code):
                    mock_response = MagicMock()
                    mock_response.status_code = status_code
                    return APIStatusError(
                        message=f"Error {status_code}",
                        response=mock_response,
                        body=None,
                    )

                # Retryable codes
                assert client._is_retryable_error(make_api_error(429))
                assert client._is_retryable_error(make_api_error(500))
                assert client._is_retryable_error(make_api_error(503))

                # Non-retryable codes
                assert not client._is_retryable_error(make_api_error(400))
                assert not client._is_retryable_error(make_api_error(401))
                assert not client._is_retryable_error(make_api_error(404))

    @pytest.mark.asyncio
    async def test_calculate_backoff(self):
        """Should calculate exponential backoff with jitter."""
        with patch("services.llm.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                nvidia_api_key="test",
                nvidia_model="test",
                redis_url="redis://localhost",
                rate_limit_requests=30,
                rate_limit_window=60,
                llm_max_retries=3,
                llm_retry_base_delay=1.0,
                max_prompt_tokens=12000,
                prompt_warning_threshold=0.8,
            )
            mock_settings.return_value.get_nvidia_api_key = MagicMock(
                return_value="test"
            )

            with patch("services.llm.AsyncOpenAI"):
                client = LLMClient()

                # Test multiple times to account for jitter
                for _ in range(10):
                    backoff_0 = client._calculate_backoff(0)
                    backoff_1 = client._calculate_backoff(1)
                    backoff_2 = client._calculate_backoff(2)

                    # Base is 1 * 2^attempt, jitter adds 0-1 second
                    assert 1.0 <= backoff_0 <= 2.0  # 1 * 2^0 + jitter
                    assert 2.0 <= backoff_1 <= 3.0  # 1 * 2^1 + jitter
                    assert 4.0 <= backoff_2 <= 5.0  # 1 * 2^2 + jitter

    @pytest.mark.asyncio
    async def test_calculate_backoff_cap(self):
        """Should cap backoff at 8 seconds base."""
        with patch("services.llm.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                nvidia_api_key="test",
                nvidia_model="test",
                redis_url="redis://localhost",
                rate_limit_requests=30,
                rate_limit_window=60,
                llm_max_retries=3,
                llm_retry_base_delay=1.0,
                max_prompt_tokens=12000,
                prompt_warning_threshold=0.8,
            )
            mock_settings.return_value.get_nvidia_api_key = MagicMock(
                return_value="test"
            )

            with patch("services.llm.AsyncOpenAI"):
                client = LLMClient()

                # High attempt numbers should be capped
                backoff = client._calculate_backoff(10)
                assert 8.0 <= backoff <= 9.0  # 8 + jitter (capped)

    @pytest.mark.asyncio
    async def test_generate_success_no_retry(self, mock_openai_response, mock_redis):
        """Should succeed without retry on first attempt."""
        with patch("services.llm.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                nvidia_api_key="test",
                nvidia_model="test",
                redis_url="redis://localhost",
                rate_limit_requests=30,
                rate_limit_window=60,
                llm_max_retries=3,
                llm_retry_base_delay=1.0,
                max_prompt_tokens=12000,
                prompt_warning_threshold=0.8,
            )
            mock_settings.return_value.get_nvidia_api_key = MagicMock(
                return_value="test"
            )

            with patch("services.llm.AsyncOpenAI") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.chat.completions.create = AsyncMock(
                    return_value=mock_openai_response
                )
                mock_client_class.return_value = mock_client

                with patch("services.llm.redis") as mock_redis_module:
                    mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                    client = LLMClient()
                    result = await client.generate("Test prompt")

                    assert result == "Test response"
                    # Should only be called once (no retries)
                    assert mock_client.chat.completions.create.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_retry_on_transient_error(
        self, mock_openai_response, mock_redis
    ):
        """Should retry on transient errors."""
        with patch("services.llm.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                nvidia_api_key="test",
                nvidia_model="test",
                redis_url="redis://localhost",
                rate_limit_requests=30,
                rate_limit_window=60,
                llm_max_retries=3,
                llm_retry_base_delay=1.0,
                max_prompt_tokens=12000,
                prompt_warning_threshold=0.8,
            )
            mock_settings.return_value.get_nvidia_api_key = MagicMock(
                return_value="test"
            )

            with patch("services.llm.AsyncOpenAI") as mock_client_class:
                mock_client = AsyncMock()
                # First call fails, second succeeds
                mock_client.chat.completions.create = AsyncMock(
                    side_effect=[
                        ConnectionError("Connection failed"),
                        mock_openai_response,
                    ]
                )
                mock_client_class.return_value = mock_client

                with patch("services.llm.redis") as mock_redis_module:
                    mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                    # Patch sleep to avoid waiting
                    with patch("asyncio.sleep", new_callable=AsyncMock):
                        client = LLMClient()
                        result = await client.generate("Test prompt", max_retries=3)

                        assert result == "Test response"
                        # Should be called twice (1 fail + 1 success)
                        assert mock_client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_generate_max_retries_exceeded(self, mock_redis):
        """Should raise after max retries exceeded."""
        with patch("services.llm.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                nvidia_api_key="test",
                nvidia_model="test",
                redis_url="redis://localhost",
                rate_limit_requests=30,
                rate_limit_window=60,
                llm_max_retries=2,
                llm_retry_base_delay=1.0,
                max_prompt_tokens=12000,
                prompt_warning_threshold=0.8,
            )
            mock_settings.return_value.get_nvidia_api_key = MagicMock(
                return_value="test"
            )

            with patch("services.llm.AsyncOpenAI") as mock_client_class:
                mock_client = AsyncMock()
                # Always fail with retryable error
                mock_client.chat.completions.create = AsyncMock(
                    side_effect=ConnectionError("Connection failed")
                )
                mock_client_class.return_value = mock_client

                with patch("services.llm.redis") as mock_redis_module:
                    mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                    # Patch sleep to avoid waiting
                    with patch("asyncio.sleep", new_callable=AsyncMock):
                        client = LLMClient()

                        with pytest.raises(ConnectionError):
                            await client.generate("Test prompt", max_retries=2)

                        # Should be called 3 times (1 initial + 2 retries)
                        assert mock_client.chat.completions.create.call_count == 3

    @pytest.mark.asyncio
    async def test_generate_no_retry_on_non_retryable_error(self, mock_redis):
        """Should not retry on non-retryable errors."""
        with patch("services.llm.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                nvidia_api_key="test",
                nvidia_model="test",
                redis_url="redis://localhost",
                rate_limit_requests=30,
                rate_limit_window=60,
                llm_max_retries=3,
                llm_retry_base_delay=1.0,
                max_prompt_tokens=12000,
                prompt_warning_threshold=0.8,
            )
            mock_settings.return_value.get_nvidia_api_key = MagicMock(
                return_value="test"
            )

            with patch("services.llm.AsyncOpenAI") as mock_client_class:
                mock_client = AsyncMock()

                # Create a 400 Bad Request error (non-retryable)
                mock_response = MagicMock()
                mock_response.status_code = 400
                mock_client.chat.completions.create = AsyncMock(
                    side_effect=APIStatusError(
                        message="Bad Request",
                        response=mock_response,
                        body=None,
                    )
                )
                mock_client_class.return_value = mock_client

                with patch("services.llm.redis") as mock_redis_module:
                    mock_redis_module.from_url = MagicMock(return_value=mock_redis)

                    client = LLMClient()

                    with pytest.raises(APIStatusError):
                        await client.generate("Test prompt", max_retries=3)

                    # Should only be called once (no retries for 400)
                    assert mock_client.chat.completions.create.call_count == 1


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
