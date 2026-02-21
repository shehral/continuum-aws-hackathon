"""Prometheus metrics for the Continuum API.

This module provides application-level metrics exposed via /metrics endpoint.
Metrics follow Prometheus naming conventions and include:
- Request counters and latency histograms
- Database connection pool gauges
- LLM API call counters
- Cache hit/miss counters
"""

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Use a custom registry to avoid conflicts with default registry
REGISTRY = CollectorRegistry()

# Request metrics
REQUEST_COUNT = Counter(
    "continuum_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
    registry=REGISTRY,
)

REQUEST_DURATION = Histogram(
    "continuum_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

# Database connection pools
POSTGRES_POOL_SIZE = Gauge(
    "continuum_postgres_pool_size",
    "PostgreSQL connection pool size",
    registry=REGISTRY,
)

POSTGRES_POOL_CHECKED_OUT = Gauge(
    "continuum_postgres_pool_checked_out",
    "PostgreSQL connections currently in use",
    registry=REGISTRY,
)

NEO4J_POOL_SIZE = Gauge(
    "continuum_neo4j_pool_size",
    "Neo4j connection pool max size",
    registry=REGISTRY,
)

NEO4J_POOL_IN_USE = Gauge(
    "continuum_neo4j_pool_in_use",
    "Neo4j connections currently in use",
    registry=REGISTRY,
)

REDIS_POOL_SIZE = Gauge(
    "continuum_redis_pool_size",
    "Redis connection pool size",
    registry=REGISTRY,
)

REDIS_POOL_IN_USE = Gauge(
    "continuum_redis_pool_in_use",
    "Redis connections currently in use",
    registry=REGISTRY,
)

# LLM API metrics
LLM_REQUESTS_TOTAL = Counter(
    "continuum_llm_requests_total",
    "Total LLM API requests",
    ["model", "status"],
    registry=REGISTRY,
)

LLM_REQUEST_DURATION = Histogram(
    "continuum_llm_request_duration_seconds",
    "LLM API request latency in seconds",
    ["model"],
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
    registry=REGISTRY,
)

LLM_TOKENS_TOTAL = Counter(
    "continuum_llm_tokens_total",
    "Total tokens processed by LLM",
    ["model", "type"],  # type: prompt, completion
    registry=REGISTRY,
)

# Cache metrics
CACHE_HITS = Counter(
    "continuum_cache_hits_total",
    "Total cache hits",
    ["cache_type"],
    registry=REGISTRY,
)

CACHE_MISSES = Counter(
    "continuum_cache_misses_total",
    "Total cache misses",
    ["cache_type"],
    registry=REGISTRY,
)

# Entity resolution metrics
ENTITY_RESOLUTION_TOTAL = Counter(
    "continuum_entity_resolution_total",
    "Total entity resolution attempts",
    [
        "method",
        "result",
    ],  # method: exact, canonical, alias, fuzzy, embedding; result: found, not_found
    registry=REGISTRY,
)

# Application info gauge
APP_INFO = Gauge(
    "continuum_app_info",
    "Application information",
    ["version", "environment"],
    registry=REGISTRY,
)


def get_metrics() -> bytes:
    """Generate Prometheus metrics output."""
    return generate_latest(REGISTRY)


def set_app_info(version: str, environment: str):
    """Set application info gauge."""
    APP_INFO.labels(version=version, environment=environment).set(1)
