"""LLM client with per-user rate limiting, retry logic, request size validation, and model fallback.

Supports multiple LLM providers (NVIDIA NIM, Amazon Bedrock) via the provider abstraction layer.
SEC-009: Implements per-user rate limiting instead of global rate limiting.
ML-QW-2: Model fallback support - if primary model fails, automatically fall back to secondary model.
"""

import asyncio
import random
import re
import time
from typing import AsyncIterator

import redis.asyncio as redis
from openai import APIConnectionError, APIStatusError, APITimeoutError

from config import get_settings
from services.llm_providers import get_llm_provider
from services.datadog_logger import DatadogLLMLogger, LLMCallTimer
from utils.logging import get_logger
from utils.prompt_sanitizer import InjectionRiskLevel, sanitize_prompt

logger = get_logger(__name__)


def strip_thinking_tags(text: str) -> str:
    """Remove <think>...</think> tags from model output.

    Handles various formats:
    - <think>...</think>  (Nemotron/DeepSeek style)
    - <think attr>...</think>  (any attributes)
    - <thinking>...</thinking>
    - Unclosed tags (removes from opening tag to true end-of-string)
    """
    if not text:
        return text

    # Remove properly closed thinking blocks.
    # r"<think\b[^>]*>" matches <think>, <think >, <think mode="fast">, etc.
    patterns = [
        r"<think\b[^>]*>.*?</think>\s*",
        r"<thinking\b[^>]*>.*?</thinking>\s*",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

    # Handle unclosed tags — consume everything from the opening tag to the
    # true end of the string.  Use \Z (not $) so re.DOTALL doesn't stop at \n.
    unclosed_patterns = [
        r"<think\b[^>]*>.*\Z",
        r"<thinking\b[^>]*>.*\Z",
    ]
    for pattern in unclosed_patterns:
        text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

    return text.strip()


# HTTP status codes that should trigger a retry
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Overhead tokens for message formatting (role labels, special tokens, etc.)
MESSAGE_OVERHEAD_TOKENS = 10

# Default rate limits (SEC-009)
DEFAULT_RATE_LIMIT_REQUESTS = 30  # Per minute for authenticated users
DEFAULT_RATE_LIMIT_WINDOW = 60  # Window in seconds
ANONYMOUS_RATE_LIMIT_REQUESTS = 10  # Stricter limit for anonymous users


class PromptTooLargeError(ValueError):
    """Raised when the prompt exceeds the maximum allowed token count."""

    def __init__(
        self, estimated_tokens: int, max_tokens: int, message: str | None = None
    ):
        self.estimated_tokens = estimated_tokens
        self.max_tokens = max_tokens
        if message is None:
            message = (
                f"Prompt too large: estimated {estimated_tokens} tokens, "
                f"max allowed is {max_tokens} tokens"
            )
        super().__init__(message)


class RateLimitExceededError(Exception):
    """Raised when rate limit is exceeded (SEC-009)."""

    def __init__(self, user_id: str, retry_after: float = 30.0):
        self.user_id = user_id
        self.retry_after = retry_after
        super().__init__(
            f"Rate limit exceeded for user. Please retry after {retry_after:.0f} seconds."
        )


class PromptInjectionError(ValueError):
    """Raised when a prompt injection attempt is detected (ML-P1-1)."""

    def __init__(
        self,
        risk_level: InjectionRiskLevel,
        patterns: list[str],
        message: str | None = None,
    ):
        self.risk_level = risk_level
        self.patterns = patterns
        if message is None:
            message = (
                f"Potential prompt injection detected (risk: {risk_level.value}). "
                f"Detected patterns: {', '.join(patterns[:3])}"
            )
        super().__init__(message)


class RateLimiter:
    """Token bucket rate limiter using Redis with per-user support (SEC-009).

    Supports both per-user and global rate limiting:
    - Per-user: Uses key format 'ratelimit:user:{user_id}:nvidia_api'
    - Global: Uses key format 'ratelimit:global:nvidia_api'

    Anonymous users get stricter rate limits than authenticated users.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        user_id: str | None = None,
        max_requests: int | None = None,
        window: int | None = None,
    ):
        """Initialize rate limiter.

        Args:
            redis_client: Redis async client
            user_id: User ID for per-user limiting. If None or "anonymous",
                     uses stricter anonymous limits.
            max_requests: Max requests per window. Defaults based on user type.
            window: Window size in seconds.
        """
        self.redis = redis_client
        self.user_id = user_id or "anonymous"

        # Set window (default 60 seconds)
        settings = get_settings()
        self.window = window or settings.rate_limit_window

        # Determine rate limit based on user type (SEC-009)
        if self.user_id == "anonymous":
            self.max_requests = max_requests or ANONYMOUS_RATE_LIMIT_REQUESTS
            self.key = "ratelimit:anonymous:nvidia_api"
        else:
            self.max_requests = max_requests or settings.rate_limit_requests
            # Per-user key format for isolation
            self.key = f"ratelimit:user:{self.user_id}:nvidia_api"

        logger.debug(
            f"Rate limiter initialized: user={self.user_id[:8]}..., "
            f"limit={self.max_requests}/{self.window}s"
        )

    async def acquire(self) -> bool:
        """Try to acquire a rate limit token. Returns True if allowed."""
        now = time.time()
        window_start = now - self.window

        pipe = self.redis.pipeline()
        # Remove old entries
        pipe.zremrangebyscore(self.key, 0, window_start)
        # Count current entries
        pipe.zcard(self.key)
        # Add new entry
        pipe.zadd(self.key, {str(now): now})
        # Set expiry
        pipe.expire(self.key, self.window)

        results = await pipe.execute()
        current_count = results[1]

        if current_count >= self.max_requests:
            # Remove the entry we just added
            await self.redis.zrem(self.key, str(now))
            logger.warning(
                f"Rate limit exceeded: user={self.user_id[:8] if len(self.user_id) > 8 else self.user_id}, "
                f"count={current_count}/{self.max_requests}"
            )
            return False
        return True

    async def get_remaining(self) -> tuple[int, float]:
        """Get remaining requests and time until window reset.

        Returns:
            Tuple of (remaining_requests, seconds_until_reset)
        """
        now = time.time()
        window_start = now - self.window

        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(self.key, 0, window_start)
        pipe.zcard(self.key)
        pipe.zrange(self.key, 0, 0, withscores=True)

        results = await pipe.execute()
        current_count = results[1]
        oldest_entry = results[2]

        remaining = max(0, self.max_requests - current_count)

        # Calculate time until oldest entry expires
        if oldest_entry:
            oldest_time = oldest_entry[0][1]
            seconds_until_reset = max(0, oldest_time + self.window - now)
        else:
            seconds_until_reset = 0

        return remaining, seconds_until_reset

    async def wait_for_slot(self, timeout: float = 30.0) -> bool:
        """Wait until a rate limit slot is available."""
        start = time.time()
        while time.time() - start < timeout:
            if await self.acquire():
                return True
            await asyncio.sleep(0.5)
        return False


class LLMClient:
    """LLM client with per-user rate limiting, retry logic, size validation, and model fallback.

    Supports NVIDIA NIM and Amazon Bedrock providers via the provider abstraction layer.

    Features:
    - Per-user token bucket rate limiting via Redis (SEC-009)
    - Different limits for authenticated vs anonymous users
    - Exponential backoff with jitter for transient failures
    - Retries on 429, 500, 502, 503, 504 status codes
    - Thinking tag stripping from model output
    - Request size validation to prevent oversized prompts (ML-P1-3)
    - Model fallback support (ML-QW-2): Falls back to secondary model if primary fails
    """

    def __init__(self):
        self.settings = get_settings()
        self.provider = get_llm_provider()
        self.model = self.provider.model_name
        # ML-QW-2: Fallback model configuration
        self.fallback_model = self.settings.llm_fallback_model
        self.fallback_enabled = self.settings.llm_fallback_enabled
        self._fallback_provider = None
        self._redis: redis.Redis | None = None
        # Cache rate limiters by user_id to avoid recreating
        self._rate_limiters: dict[str, RateLimiter] = {}

    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(self.settings.redis_url)
        return self._redis

    async def _get_rate_limiter(self, user_id: str | None = None) -> RateLimiter:
        """Get or create rate limiter for a specific user (SEC-009).

        Args:
            user_id: User ID for per-user rate limiting.
                     If None, uses global rate limiting.

        Returns:
            RateLimiter instance for the user
        """
        key = user_id or "anonymous"

        if key not in self._rate_limiters:
            redis_client = await self._get_redis()
            self._rate_limiters[key] = RateLimiter(
                redis_client,
                user_id=user_id,
                max_requests=self.settings.rate_limit_requests,
                window=self.settings.rate_limit_window,
            )

        return self._rate_limiters[key]

    def _get_fallback_provider(self):
        """Get or create the fallback LLM provider (ML-QW-2).

        Fallback is only available for the NVIDIA provider (uses a different model
        on the same API). Bedrock handles retries at the AWS level.
        """
        if not self.fallback_enabled or not self.fallback_model:
            return None
        if self._fallback_provider is None and self.settings.llm_provider == "nvidia":
            from services.llm_providers.nvidia import NvidiaLLMProvider

            self._fallback_provider = NvidiaLLMProvider(model=self.fallback_model)
        return self._fallback_provider

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for a piece of text.

        Uses a simple heuristic: approximately 4 characters per token for English text.
        This is a conservative estimate that works well for most LLMs including Llama.

        Note: For more accurate counting, consider using tiktoken or the model's
        actual tokenizer, but this adds latency and dependencies.

        Args:
            text: The text to estimate tokens for

        Returns:
            Estimated token count
        """
        if not text:
            return 0
        # Rough estimate: 4 characters per token (conservative for English)
        # This is faster than actual tokenization and sufficient for pre-flight checks
        return len(text) // 4 + 1

    def _estimate_messages_tokens(self, messages: list[dict]) -> int:
        """Estimate total tokens for a list of messages.

        Args:
            messages: List of message dicts with 'role' and 'content' keys

        Returns:
            Estimated total token count including message overhead
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += self._estimate_tokens(content)
            # Add overhead for role label and message formatting
            total += MESSAGE_OVERHEAD_TOKENS
        return total

    def _validate_prompt_size(
        self,
        prompt: str,
        system_prompt: str = "",
        max_prompt_tokens: int | None = None,
    ) -> int:
        """Validate that the prompt size is within limits.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            max_prompt_tokens: Override for max token limit (default: from settings)

        Returns:
            Estimated token count

        Raises:
            PromptTooLargeError: If estimated tokens exceed the limit
        """
        if max_prompt_tokens is None:
            # Use effective_max_prompt_tokens (model-aware, 85% of context limit)
            # instead of the hardcoded max_prompt_tokens default
            max_prompt_tokens = self.settings.effective_max_prompt_tokens

        # Build messages to estimate
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        estimated_tokens = self._estimate_messages_tokens(messages)

        # Check if we're at or over the limit
        if estimated_tokens > max_prompt_tokens:
            logger.error(
                f"Prompt size validation failed: estimated {estimated_tokens} tokens "
                f"exceeds max {max_prompt_tokens} tokens"
            )
            raise PromptTooLargeError(estimated_tokens, max_prompt_tokens)

        # Warn if approaching limit (> 80%)
        warning_threshold = max_prompt_tokens * 0.8
        if estimated_tokens > warning_threshold:
            logger.warning(
                f"Prompt size approaching limit: estimated {estimated_tokens} tokens "
                f"({estimated_tokens / max_prompt_tokens * 100:.1f}% of {max_prompt_tokens} max)"
            )

        return estimated_tokens

    def _sanitize_user_prompt(
        self,
        prompt: str,
        reject_high_risk: bool = True,
    ) -> str:
        """Sanitize user prompt to prevent prompt injection (ML-P1-1).

        Args:
            prompt: The user prompt to sanitize
            reject_high_risk: If True, raise error on HIGH/CRITICAL risk prompts

        Returns:
            Sanitized prompt

        Raises:
            PromptInjectionError: If prompt is high risk and reject_high_risk=True
        """
        result = sanitize_prompt(prompt)

        # Log any detected patterns
        if result.detected_patterns:
            logger.warning(
                "Prompt injection patterns detected",
                extra={
                    "risk_level": result.risk_level.value,
                    "confidence": result.confidence,
                    "pattern_count": len(result.detected_patterns),
                    "was_modified": result.was_modified,
                },
            )

        # Reject high-risk prompts
        if reject_high_risk and result.risk_level in (
            InjectionRiskLevel.HIGH,
            InjectionRiskLevel.CRITICAL,
        ):
            raise PromptInjectionError(
                result.risk_level,
                result.detected_patterns,
            )

        return result.sanitized_text

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff with jitter.

        Args:
            attempt: The current retry attempt number (0-indexed)

        Returns:
            Sleep duration in seconds
        """
        # Exponential backoff: base * 2^attempt, capped at 8 seconds
        base_delay = self.settings.llm_retry_base_delay
        exponential = min(base_delay * (2**attempt), 8.0)
        # Add jitter: 0-1 seconds to prevent thundering herd
        jitter = random.uniform(0, 1)
        return exponential + jitter

    def _should_fallback(self, error: Exception) -> bool:
        """Check if an error should trigger fallback to secondary model (ML-QW-2).

        Fallback is appropriate for:
        - Model-specific errors (model overloaded, not available)
        - Persistent failures after retries
        - Non-transient API errors

        Args:
            error: The exception that was raised

        Returns:
            True if fallback should be attempted
        """
        if not self.fallback_enabled:
            return False

        # Check for model-specific errors that warrant fallback
        if isinstance(error, APIStatusError):
            # Model unavailable, service overloaded, or quota exceeded
            if error.status_code in {503, 529}:  # 529 = model overloaded on some APIs
                return True
            # Check error message for model-specific issues
            error_msg = str(error).lower()
            if any(
                phrase in error_msg
                for phrase in ["model", "overloaded", "capacity", "unavailable"]
            ):
                return True

        return False

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error should trigger a retry.

        Args:
            error: The exception that was raised

        Returns:
            True if the error is transient and should be retried
        """
        # Connection and timeout errors are retryable
        if isinstance(
            error, (TimeoutError, ConnectionError, APIConnectionError, APITimeoutError)
        ):
            return True

        # API status errors with specific codes are retryable (NVIDIA/OpenAI)
        if isinstance(error, APIStatusError):
            return error.status_code in RETRYABLE_STATUS_CODES

        # Bedrock/boto3 errors
        try:
            from botocore.exceptions import ClientError

            if isinstance(error, ClientError):
                code = error.response.get("Error", {}).get("Code", "")
                return code in {
                    "ThrottlingException",
                    "ServiceUnavailableException",
                    "InternalServerException",
                }
        except ImportError:
            pass

        return False

    def _log_token_usage(self, usage, model: str, streaming: bool = False) -> None:
        """Log token usage for cost monitoring and debugging (ML-QW-1).

        Logs prompt tokens, completion tokens, and total tokens with the model name.
        Uses structured logging format for easy parsing by log aggregators.

        Args:
            usage: The usage dict (from providers) or object from the API response
            model: The model name/ID used for the request
            streaming: Whether this was a streaming request
        """
        if usage is None:
            logger.debug("Token usage not available in response")
            return

        # Handle both dict (from providers) and object (legacy) formats
        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens", 0) or 0
            completion_tokens = usage.get("completion_tokens", 0) or 0
            total_tokens = (
                usage.get("total_tokens", 0) or prompt_tokens + completion_tokens
            )
        else:
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            total_tokens = (
                getattr(usage, "total_tokens", 0) or prompt_tokens + completion_tokens
            )

        logger.info(
            "LLM token usage",
            extra={
                "token_usage": {
                    "model": model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "streaming": streaming,
                }
            },
        )

    async def _generate_with_provider(
        self,
        provider,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        max_retries: int,
        user_id: str | None = None,
        operation: str = "generate",
    ) -> str:
        """Internal method to generate completion with a specific provider (ML-QW-2).

        Args:
            provider: The LLM provider to use for generation
            messages: List of message dicts
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            max_retries: Maximum retry attempts
            user_id: User ID for tracking
            operation: Operation type for logging

        Returns:
            The generated text with thinking tags stripped

        Raises:
            Exception: If max retries exceeded
        """
        model = provider.model_name
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                # Time the LLM call
                with LLMCallTimer() as timer:
                    text, usage = await provider.generate(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )

                # Log token usage for cost monitoring (ML-QW-1)
                self._log_token_usage(usage, model, streaming=False)

                # Log to Datadog
                print(f"[DEBUG] About to log to Datadog: {model}, {usage.get('total_tokens', 0)} tokens")
                await DatadogLLMLogger.log_llm_call(
                    model=model,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    latency_ms=timer.elapsed_ms,
                    operation=operation,
                    streaming=False,
                    user_id=user_id,
                    success=True,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                return strip_thinking_tags(text)

            except Exception as e:
                last_error = e

                # Log failure to Datadog
                if attempt >= max_retries:
                    await DatadogLLMLogger.log_llm_call(
                        model=model,
                        prompt_tokens=0,
                        completion_tokens=0,
                        total_tokens=0,
                        latency_ms=0,
                        operation=operation,
                        streaming=False,
                        user_id=user_id,
                        success=False,
                        error=f"{type(e).__name__}: {str(e)}",
                    )

                # Don't retry non-retryable errors
                if not self._is_retryable_error(e):
                    logger.error(
                        f"Non-retryable error on LLM call with {model}: {type(e).__name__}: {e}"
                    )
                    raise

                # Don't retry if we've exhausted attempts
                if attempt >= max_retries:
                    logger.error(
                        f"LLM call with {model} failed after {max_retries + 1} attempts. "
                        f"Last error: {type(e).__name__}: {e}"
                    )
                    raise

                # Calculate backoff and retry
                backoff = self._calculate_backoff(attempt)
                logger.warning(
                    f"Retryable error on attempt {attempt + 1}/{max_retries + 1} with {model}: "
                    f"{type(e).__name__}: {e}. Retrying in {backoff:.2f}s"
                )
                await asyncio.sleep(backoff)

        if last_error:
            raise last_error
        raise Exception("Unexpected error in LLM generate")

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.6,
        max_tokens: int = 4096,
        max_retries: int | None = None,
        validate_size: bool = True,
        user_id: str | None = None,
        sanitize_input: bool = True,
    ) -> str:
        """Generate a completion (non-streaming) with retry logic and model fallback.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            max_retries: Maximum retry attempts (default: from settings)
            validate_size: Whether to validate prompt size before sending
            user_id: User ID for per-user rate limiting (SEC-009)
            sanitize_input: Whether to sanitize prompt for injection attacks (ML-P1-1)

        Returns:
            The generated text with thinking tags stripped

        Raises:
            PromptTooLargeError: If prompt exceeds max_prompt_tokens (when validate_size=True)
            PromptInjectionError: If prompt injection detected (when sanitize_input=True)
            RateLimitExceededError: If rate limit exceeded after timeout
            Exception: If max retries exceeded on both primary and fallback models
        """
        if max_retries is None:
            max_retries = self.settings.llm_max_retries

        # Sanitize prompt for injection attempts (ML-P1-1)
        if sanitize_input:
            prompt = self._sanitize_user_prompt(prompt)

        # Validate prompt size before making API call (ML-P1-3)
        if validate_size:
            self._validate_prompt_size(prompt, system_prompt)

        # Get per-user rate limiter (SEC-009)
        rate_limiter = await self._get_rate_limiter(user_id)

        if not await rate_limiter.wait_for_slot():
            remaining, retry_after = await rate_limiter.get_remaining()
            raise RateLimitExceededError(user_id or "anonymous", retry_after)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Try primary provider first
        try:
            return await self._generate_with_provider(
                provider=self.provider,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                max_retries=max_retries,
                user_id=user_id,
                operation="generate",
            )
        except Exception as primary_error:
            # ML-QW-2: Check if we should fall back to secondary model
            fallback_provider = self._get_fallback_provider()
            if self._should_fallback(primary_error) and fallback_provider:
                logger.warning(
                    f"Primary model {self.model} failed, falling back to {self.fallback_model}",
                    extra={
                        "primary_model": self.model,
                        "fallback_model": self.fallback_model,
                        "primary_error": str(primary_error),
                    },
                )
                try:
                    return await self._generate_with_provider(
                        provider=fallback_provider,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        max_retries=max_retries,
                        user_id=user_id,
                        operation="generate_fallback",
                    )
                except Exception as fallback_error:
                    logger.error(
                        f"Fallback model {self.fallback_model} also failed",
                        extra={
                            "primary_model": self.model,
                            "fallback_model": self.fallback_model,
                            "primary_error": str(primary_error),
                            "fallback_error": str(fallback_error),
                        },
                    )
                    # Re-raise the fallback error as it's more recent
                    raise fallback_error
            else:
                # No fallback available or not appropriate, re-raise original error
                raise

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.6,
        max_tokens: int = 4096,
        max_retries: int | None = None,
        validate_size: bool = True,
        user_id: str | None = None,
        sanitize_input: bool = True,
    ) -> AsyncIterator[str]:
        """Generate a streaming completion with retry logic.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            max_retries: Maximum retry attempts (default: from settings)
            validate_size: Whether to validate prompt size before sending
            user_id: User ID for per-user rate limiting (SEC-009)
            sanitize_input: Whether to sanitize prompt for injection attacks (ML-P1-1)

        Yields:
            Generated text chunks with thinking tags stripped

        Raises:
            PromptTooLargeError: If prompt exceeds max_prompt_tokens (when validate_size=True)
            PromptInjectionError: If prompt injection detected (when sanitize_input=True)
            RateLimitExceededError: If rate limit exceeded after timeout
            Exception: If max retries exceeded
        """
        if max_retries is None:
            max_retries = self.settings.llm_max_retries

        # Sanitize prompt for injection attempts (ML-P1-1)
        if sanitize_input:
            prompt = self._sanitize_user_prompt(prompt)

        # Validate prompt size before making API call (ML-P1-3)
        if validate_size:
            self._validate_prompt_size(prompt, system_prompt)

        # Get per-user rate limiter (SEC-009)
        rate_limiter = await self._get_rate_limiter(user_id)

        if not await rate_limiter.wait_for_slot():
            remaining, retry_after = await rate_limiter.get_remaining()
            raise RateLimitExceededError(user_id or "anonymous", retry_after)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                # Buffer for thinking tag stripping in streaming mode
                buffer = ""
                in_thinking_block = False

                async for content in self.provider.generate_stream(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    buffer += content

                    # Handle thinking tags in streaming
                    while True:
                        if not in_thinking_block:
                            # Look for start of thinking block
                            think_start = buffer.find("<think>")
                            if think_start != -1:
                                # Yield content before the tag
                                if think_start > 0:
                                    yield buffer[:think_start]
                                buffer = buffer[think_start + 7 :]  # Skip <think>
                                in_thinking_block = True
                            else:
                                # Check if we might be at the start of a tag
                                if (
                                    buffer.endswith("<")
                                    or buffer.endswith("<t")
                                    or buffer.endswith("<th")
                                    or buffer.endswith("<thi")
                                    or buffer.endswith("<thin")
                                    or buffer.endswith("<think")
                                ):
                                    # Keep partial tag in buffer
                                    break
                                # Safe to yield everything
                                if buffer:
                                    yield buffer
                                    buffer = ""
                                break
                        else:
                            # Look for end of thinking block
                            think_end = buffer.find("</think>")
                            if think_end != -1:
                                # Discard thinking content
                                buffer = buffer[think_end + 8 :]  # Skip </think>
                                in_thinking_block = False
                            else:
                                # Still inside thinking block, keep buffering
                                break

                # Yield any remaining content (not in thinking block)
                if buffer and not in_thinking_block:
                    yield buffer

                return  # Success, exit retry loop

            except Exception as e:
                last_error = e

                # Don't retry non-retryable errors
                if not self._is_retryable_error(e):
                    logger.error(
                        f"Non-retryable error on streaming LLM call: {type(e).__name__}: {e}"
                    )
                    raise

                # Don't retry if we've exhausted attempts
                if attempt >= max_retries:
                    logger.error(
                        f"Streaming LLM call failed after {max_retries + 1} attempts. "
                        f"Last error: {type(e).__name__}: {e}"
                    )
                    raise

                # Calculate backoff and retry
                backoff = self._calculate_backoff(attempt)
                logger.warning(
                    f"Retryable error on streaming attempt {attempt + 1}/{max_retries + 1}: "
                    f"{type(e).__name__}: {e}. Retrying in {backoff:.2f}s"
                )
                await asyncio.sleep(backoff)

        # This should never be reached, but just in case
        if last_error:
            raise last_error

    async def close(self):
        """Close connections."""
        if self._redis:
            await self._redis.close()
        self._rate_limiters.clear()


# Singleton instance
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Get the LLM client singleton."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
