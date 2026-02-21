"""Shared utilities for the Continuum API."""

from utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitState,
    get_all_circuit_breakers,
    get_circuit_breaker,
    get_circuit_breaker_stats,
)
from utils.json_extraction import extract_json_from_response, extract_json_or_default
from utils.retry import (
    RetryExhausted,
    calculate_backoff,
    neo4j_retry,
    postgres_retry,
    redis_retry,
    retry,
)
from utils.vectors import cosine_similarity

__all__ = [
    # Vector utilities
    "cosine_similarity",
    # JSON extraction
    "extract_json_from_response",
    "extract_json_or_default",
    # Circuit breaker (SD-006)
    "CircuitBreaker",
    "CircuitBreakerOpen",
    "CircuitState",
    "get_circuit_breaker",
    "get_all_circuit_breakers",
    "get_circuit_breaker_stats",
    # Retry utilities (SD-009)
    "retry",
    "calculate_backoff",
    "RetryExhausted",
    "postgres_retry",
    "neo4j_retry",
    "redis_retry",
]
