"""Circuit breaker pattern for resilience against cascading failures (SD-006).

This module implements the circuit breaker pattern to prevent cascading failures
when external services (NVIDIA API, databases) are unavailable or slow.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Circuit is tripped, requests fail fast without calling the service
- HALF_OPEN: Testing if service has recovered, limited requests allowed

Usage:
    from utils.circuit_breaker import CircuitBreaker, CircuitBreakerOpen

    # Create a circuit breaker for external service
    llm_breaker = CircuitBreaker(
        name="nvidia_llm",
        failure_threshold=5,
        recovery_timeout=30.0,
        success_threshold=2,
    )

    # Use as a decorator
    @llm_breaker
    async def call_llm(prompt: str) -> str:
        ...

    # Or use as a context manager
    async with llm_breaker:
        response = await external_call()
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, Set, Type

from utils.logging import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing fast
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is open and rejecting requests."""

    def __init__(self, name: str, time_remaining: float):
        self.name = name
        self.time_remaining = time_remaining
        super().__init__(
            f"Circuit breaker '{name}' is open. "
            f"Service unavailable. Retry in {time_remaining:.1f}s"
        )


@dataclass
class CircuitBreakerStats:
    """Statistics for a circuit breaker."""

    name: str
    state: str
    failure_count: int
    success_count: int
    last_failure_time: Optional[float]
    last_success_time: Optional[float]
    total_failures: int
    total_successes: int
    total_rejections: int


@dataclass
class CircuitBreaker:
    """Circuit breaker for protecting against cascading failures.

    Attributes:
        name: Identifier for this circuit breaker (used in logging)
        failure_threshold: Number of consecutive failures before opening circuit
        recovery_timeout: Seconds to wait before testing if service recovered
        success_threshold: Successful calls needed in half-open state to close
        exceptions: Exception types that should trip the circuit (None = all)
    """

    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    success_threshold: int = 2
    exceptions: Optional[Set[Type[Exception]]] = None

    # Internal state (not part of __init__)
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False, repr=False)
    _failure_count: int = field(default=0, init=False, repr=False)
    _success_count: int = field(default=0, init=False, repr=False)
    _last_failure_time: Optional[float] = field(default=None, init=False, repr=False)
    _last_success_time: Optional[float] = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    # Metrics
    _total_failures: int = field(default=0, init=False, repr=False)
    _total_successes: int = field(default=0, init=False, repr=False)
    _total_rejections: int = field(default=0, init=False, repr=False)

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, checking for automatic state transitions."""
        if self._state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self._last_failure_time is not None:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    # Transition to half-open to test recovery
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    logger.info(
                        f"Circuit breaker '{self.name}' transitioning to HALF_OPEN "
                        f"after {elapsed:.1f}s timeout"
                    )
        return self._state

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (failing fast)."""
        return self.state == CircuitState.OPEN

    @property
    def time_until_retry(self) -> float:
        """Get seconds until circuit will transition to half-open."""
        if self._state != CircuitState.OPEN or self._last_failure_time is None:
            return 0.0
        elapsed = time.time() - self._last_failure_time
        remaining = self.recovery_timeout - elapsed
        return max(0.0, remaining)

    def _should_trip(self, exc: Exception) -> bool:
        """Check if exception should trip the circuit."""
        if self.exceptions is None:
            return True
        return any(isinstance(exc, exc_type) for exc_type in self.exceptions)

    async def _record_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            self._total_successes += 1
            self._last_success_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    # Service has recovered, close the circuit
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info(
                        f"Circuit breaker '{self.name}' closed after "
                        f"{self.success_threshold} successful calls"
                    )
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    async def _record_failure(self, exc: Exception) -> None:
        """Record a failed call."""
        async with self._lock:
            if not self._should_trip(exc):
                return

            self._total_failures += 1
            self._last_failure_time = time.time()
            self._failure_count += 1

            if self._state == CircuitState.HALF_OPEN:
                # Failed during recovery test, reopen circuit
                self._state = CircuitState.OPEN
                self._success_count = 0
                logger.warning(
                    f"Circuit breaker '{self.name}' reopened after failure in HALF_OPEN: "
                    f"{type(exc).__name__}: {exc}"
                )
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    # Too many failures, open the circuit
                    self._state = CircuitState.OPEN
                    logger.warning(
                        f"Circuit breaker '{self.name}' opened after "
                        f"{self._failure_count} consecutive failures"
                    )

    async def _check_state(self) -> None:
        """Check if requests are allowed through the circuit."""
        state = self.state  # This triggers state transition check

        if state == CircuitState.OPEN:
            self._total_rejections += 1
            raise CircuitBreakerOpen(self.name, self.time_until_retry)

    def get_stats(self) -> CircuitBreakerStats:
        """Get current circuit breaker statistics."""
        return CircuitBreakerStats(
            name=self.name,
            state=self.state.value,
            failure_count=self._failure_count,
            success_count=self._success_count,
            last_failure_time=self._last_failure_time,
            last_success_time=self._last_success_time,
            total_failures=self._total_failures,
            total_successes=self._total_successes,
            total_rejections=self._total_rejections,
        )

    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        logger.info(f"Circuit breaker '{self.name}' manually reset")

    async def __aenter__(self) -> "CircuitBreaker":
        """Async context manager entry - check if requests are allowed."""
        await self._check_state()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> bool:
        """Async context manager exit - record success or failure."""
        if exc_val is None:
            await self._record_success()
        elif isinstance(exc_val, Exception):
            await self._record_failure(exc_val)
        # Don't suppress exceptions
        return False

    def __call__(self, func: Callable) -> Callable:
        """Decorator for wrapping async functions with circuit breaker."""

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            async with self:
                return await func(*args, **kwargs)

        return wrapper


# Registry of circuit breakers for monitoring
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    success_threshold: int = 2,
    exceptions: Optional[Set[Type[Exception]]] = None,
) -> CircuitBreaker:
    """Get or create a named circuit breaker.

    This ensures circuit breakers are singletons by name, so the same
    circuit breaker can be used across multiple function calls.

    Args:
        name: Unique name for this circuit breaker
        failure_threshold: Failures before opening circuit
        recovery_timeout: Seconds before testing recovery
        success_threshold: Successes needed to close circuit
        exceptions: Exception types that trip the circuit (None = all)

    Returns:
        CircuitBreaker instance
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            success_threshold=success_threshold,
            exceptions=exceptions,
        )
        logger.debug(f"Created circuit breaker '{name}'")
    return _circuit_breakers[name]


def get_all_circuit_breakers() -> dict[str, CircuitBreaker]:
    """Get all registered circuit breakers for monitoring."""
    return _circuit_breakers.copy()


def get_circuit_breaker_stats() -> list[CircuitBreakerStats]:
    """Get statistics for all circuit breakers."""
    return [cb.get_stats() for cb in _circuit_breakers.values()]
