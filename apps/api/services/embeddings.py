"""Embedding service using NVIDIA NV-EmbedQA model with Redis caching and circuit breaker (SD-006).

Features:
- SEC-007: API keys accessed via SecretStr.get_secret_value()
- ML-P1-2: Redis caching with configurable TTL
- SD-006: Circuit breaker pattern for resilience
- SD-QW-002: Configurable batch size (default 32) for improved throughput
"""

import hashlib
import json
from typing import List

import redis.asyncio as redis
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI

from config import get_settings
from utils.circuit_breaker import CircuitBreaker, get_circuit_breaker
from utils.logging import get_logger
from utils.vectors import cosine_similarity

logger = get_logger(__name__)


# Exceptions that should trip the circuit breaker
EMBEDDING_CIRCUIT_BREAKER_EXCEPTIONS = {
    APIConnectionError,
    APITimeoutError,
    ConnectionError,
    TimeoutError,
    OSError,
}


class EmbeddingService:
    """Generate embeddings using NVIDIA's Llama-based embedding model with Redis caching.

    SEC-007: API keys are accessed via SecretStr.get_secret_value() to prevent
    accidental exposure in logs or error messages.

    SD-006: Circuit breaker pattern protects against cascading failures when
    the embedding API is unavailable.
    """

    def __init__(self):
        settings = get_settings()
        # SEC-007: Use getter method to safely retrieve API key
        self.client = AsyncOpenAI(
            api_key=settings.get_nvidia_embedding_api_key(),
            base_url="https://integrate.api.nvidia.com/v1",
        )
        self.model = "nvidia/llama-3.2-nv-embedqa-1b-v2"
        self.dimensions = 2048  # Model output dimensions
        self._redis: redis.Redis | None = None
        self._settings = settings

        # SD-006: Circuit breaker for embedding API
        self._circuit_breaker = get_circuit_breaker(
            name="nvidia_embedding",
            failure_threshold=5,
            recovery_timeout=30.0,
            success_threshold=2,
            exceptions=EMBEDDING_CIRCUIT_BREAKER_EXCEPTIONS,
        )

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Get the circuit breaker for monitoring."""
        return self._circuit_breaker

    async def _get_redis(self) -> redis.Redis | None:
        """Get or create Redis connection for caching."""
        if self._redis is None:
            try:
                self._redis = redis.from_url(
                    self._settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self._redis.ping()
            except Exception as e:
                logger.warning(f"Redis connection failed, caching disabled: {e}")
                self._redis = None
        return self._redis

    def _get_cache_key(self, text: str, input_type: str) -> str:
        """Generate a cache key for the embedding.

        Format: emb:{model_short}:{input_type}:{hash(text)}
        """
        # Use MD5 hash of text for cache key (fast, collision-resistant enough for caching)
        text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        # Use short model name
        model_short = "nvembed"
        return f"emb:{model_short}:{input_type}:{text_hash}"

    async def _get_cached_embedding(self, cache_key: str) -> List[float] | None:
        """Try to get an embedding from cache."""
        redis_client = await self._get_redis()
        if redis_client is None:
            return None

        try:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.debug(f"Cache hit for {cache_key}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache read error: {e}")

        return None

    async def _set_cached_embedding(
        self, cache_key: str, embedding: List[float]
    ) -> None:
        """Store an embedding in cache."""
        redis_client = await self._get_redis()
        if redis_client is None:
            return

        try:
            await redis_client.setex(
                cache_key,
                self._settings.embedding_cache_ttl,
                json.dumps(embedding),
            )
            logger.debug(f"Cached embedding for {cache_key}")
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

    async def embed_text(self, text: str, input_type: str = "passage") -> List[float]:
        """
        Generate embedding for a single text with caching and circuit breaker.

        Args:
            text: The text to embed
            input_type: "query" for search queries, "passage" for documents

        Returns:
            List of floats representing the embedding vector

        Raises:
            CircuitBreakerOpen: If the embedding service circuit is open
        """
        # Skip cache for very short texts
        if len(text) >= self._settings.embedding_cache_min_text_length:
            cache_key = self._get_cache_key(text, input_type)
            cached = await self._get_cached_embedding(cache_key)
            if cached is not None:
                return cached

        # SD-006: Check circuit breaker before making API call
        await self._circuit_breaker._check_state()

        try:
            # Generate embedding from API
            response = await self.client.embeddings.create(
                input=[text],
                model=self.model,
                encoding_format="float",
                extra_body={"input_type": input_type, "truncate": "END"},
            )
            embedding = response.data[0].embedding

            # SD-006: Record success
            await self._circuit_breaker._record_success()

            # Cache the result (if text is long enough)
            if len(text) >= self._settings.embedding_cache_min_text_length:
                await self._set_cached_embedding(cache_key, embedding)

            return embedding

        except Exception as e:
            # SD-006: Record failure
            await self._circuit_breaker._record_failure(e)
            raise

    async def embed_texts(
        self,
        texts: List[str],
        input_type: str = "passage",
        batch_size: int | None = None,
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts with batch-aware caching and circuit breaker.

        Args:
            texts: List of texts to embed
            input_type: "query" for search queries, "passage" for documents
            batch_size: Number of texts per API call (default: settings.embedding_batch_size=32)
                        SD-QW-002: Increased from 10 to 32 for better throughput.
                        Tradeoff: Larger batches reduce API calls (helpful with 30 req/min limit)
                        but increase memory per request. NVIDIA NIM supports up to ~256 texts.

        Returns:
            List of embedding vectors

        Raises:
            CircuitBreakerOpen: If the embedding service circuit is open
        """
        # SD-QW-002: Use configurable batch size from settings (default 32)
        if batch_size is None:
            batch_size = self._settings.embedding_batch_size
        # Check cache for all texts
        results: List[List[float] | None] = [None] * len(texts)
        texts_to_embed: List[tuple[int, str]] = []  # (original_index, text)

        for i, text in enumerate(texts):
            if len(text) >= self._settings.embedding_cache_min_text_length:
                cache_key = self._get_cache_key(text, input_type)
                cached = await self._get_cached_embedding(cache_key)
                if cached is not None:
                    results[i] = cached
                    continue
            texts_to_embed.append((i, text))

        # Log cache stats
        cache_hits = len(texts) - len(texts_to_embed)
        if cache_hits > 0:
            logger.info(f"Embedding cache: {cache_hits}/{len(texts)} hits")

        # Generate embeddings for cache misses
        if texts_to_embed:
            # SD-006: Check circuit breaker before making API calls
            await self._circuit_breaker._check_state()

            try:
                # Batch the API calls
                for batch_start in range(0, len(texts_to_embed), batch_size):
                    batch = texts_to_embed[batch_start : batch_start + batch_size]
                    batch_texts = [text for _, text in batch]

                    response = await self.client.embeddings.create(
                        input=batch_texts,
                        model=self.model,
                        encoding_format="float",
                        extra_body={"input_type": input_type, "truncate": "END"},
                    )

                    # Store results and cache them
                    for j, embedding_data in enumerate(response.data):
                        original_idx, text = batch[j]
                        embedding = embedding_data.embedding
                        results[original_idx] = embedding

                        # Cache the result
                        if len(text) >= self._settings.embedding_cache_min_text_length:
                            cache_key = self._get_cache_key(text, input_type)
                            await self._set_cached_embedding(cache_key, embedding)

                # SD-006: Record success after all batches complete
                await self._circuit_breaker._record_success()

            except Exception as e:
                # SD-006: Record failure
                await self._circuit_breaker._record_failure(e)
                raise

        # Convert None to empty lists (shouldn't happen, but be safe)
        return [r if r is not None else [] for r in results]

    async def embed_decision(self, decision: dict) -> List[float]:
        """
        Generate embedding for a decision by combining its key fields.

        Creates a rich text representation that captures the full context.
        """
        # Combine all relevant fields into a semantic representation
        text_parts = [
            f"Decision Trigger: {decision.get('trigger', '')}",
            f"Context: {decision.get('context', '')}",
            f"Options Considered: {', '.join(decision.get('options', []))}",
            f"Final Decision: {decision.get('decision', '')}",
            f"Rationale: {decision.get('rationale', '')}",
        ]
        combined_text = "\n".join(text_parts)
        return await self.embed_text(combined_text, input_type="passage")

    async def embed_entity(self, entity: dict) -> List[float]:
        """
        Generate embedding for an entity.
        """
        text = f"{entity.get('type', 'concept')}: {entity.get('name', '')}"
        return await self.embed_text(text, input_type="passage")

    async def semantic_search(
        self, query: str, candidates: List[dict], top_k: int = 10
    ) -> List[dict]:
        """
        Perform semantic search over candidates.

        Args:
            query: Search query
            candidates: List of dicts with 'text' and 'embedding' fields
            top_k: Number of results to return

        Returns:
            Top-k most similar candidates with similarity scores
        """
        query_embedding = await self.embed_text(query, input_type="query")

        # Calculate cosine similarity
        scored = []
        for candidate in candidates:
            if "embedding" in candidate:
                similarity = cosine_similarity(query_embedding, candidate["embedding"])
                scored.append({**candidate, "similarity": similarity})

        # Sort by similarity descending
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]

    async def close(self):
        """Close connections."""
        if self._redis:
            await self._redis.close()


# Singleton instance
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get the embedding service singleton."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
