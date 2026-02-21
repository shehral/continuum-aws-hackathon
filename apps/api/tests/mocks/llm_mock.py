"""Mock LLM and Embedding services for unit testing.

These mocks provide deterministic, controllable responses for testing
AI-dependent code without making actual API calls.
"""

import json
from typing import Optional

from utils.vectors import cosine_similarity


class MockLLMClient:
    """Mock LLM client for testing decision extraction and analysis.

    Provides configurable responses that can be set up for different
    prompt patterns or return consistent values.
    """

    def __init__(self):
        self._responses: dict[str, str] = {}
        self._default_response = "Mock LLM response"
        self._call_history: list[dict] = []

    def set_response(self, prompt_pattern: str, response: str):
        """Set response for prompts containing the pattern."""
        self._responses[prompt_pattern.lower()] = response

    def set_json_response(self, prompt_pattern: str, data: dict):
        """Set JSON response for prompts containing the pattern."""
        self._responses[prompt_pattern.lower()] = json.dumps(data)

    def set_default_response(self, response: str):
        """Set the default response for unmatched prompts."""
        self._default_response = response

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Generate a mock response."""
        self._call_history.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )

        # Find matching response
        prompt_lower = prompt.lower()
        for pattern, response in self._responses.items():
            if pattern in prompt_lower:
                return response

        return self._default_response

    def get_call_count(self) -> int:
        """Get number of generate calls."""
        return len(self._call_history)

    def get_last_call(self) -> Optional[dict]:
        """Get the most recent call arguments."""
        return self._call_history[-1] if self._call_history else None

    def reset(self):
        """Reset all state."""
        self._responses.clear()
        self._call_history.clear()
        self._default_response = "Mock LLM response"


class MockEmbeddingService:
    """Mock embedding service for testing semantic search.

    Generates deterministic embeddings based on text content,
    allowing predictable similarity calculations.
    """

    def __init__(self, dimensions: int = 2048):
        self.dimensions = dimensions
        self._text_embeddings: dict[str, list[float]] = {}
        self._call_history: list[dict] = []

    def set_embedding(self, text: str, embedding: list[float]):
        """Set a specific embedding for a text."""
        self._text_embeddings[text.lower()] = embedding

    def _generate_deterministic_embedding(self, text: str) -> list[float]:
        """Generate a deterministic embedding based on text hash."""
        # Use hash for reproducibility
        seed = hash(text.lower()) % 1000000
        return [float((seed + i) % 100) / 100.0 for i in range(self.dimensions)]

    async def embed_text(
        self,
        text: str,
        input_type: str = "passage",
    ) -> list[float]:
        """Generate embedding for text."""
        self._call_history.append(
            {
                "method": "embed_text",
                "text": text,
                "input_type": input_type,
            }
        )

        # Return preset embedding if available
        if text.lower() in self._text_embeddings:
            return self._text_embeddings[text.lower()]

        return self._generate_deterministic_embedding(text)

    async def embed_texts(
        self,
        texts: list[str],
        input_type: str = "passage",
        batch_size: int | None = None,  # SD-QW-002: Default is 32 via settings
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        self._call_history.append(
            {
                "method": "embed_texts",
                "texts": texts,
                "input_type": input_type,
            }
        )

        return [
            self._text_embeddings.get(
                t.lower(), self._generate_deterministic_embedding(t)
            )
            for t in texts
        ]

    async def embed_decision(self, decision: dict) -> list[float]:
        """Generate embedding for a decision."""
        text = f"{decision.get('trigger', '')} {decision.get('decision', '')}"
        return await self.embed_text(text, input_type="passage")

    async def embed_entity(self, entity: dict) -> list[float]:
        """Generate embedding for an entity."""
        text = f"{entity.get('type', 'concept')}: {entity.get('name', '')}"
        return await self.embed_text(text, input_type="passage")

    async def semantic_search(
        self,
        query: str,
        candidates: list[dict],
        top_k: int = 10,
    ) -> list[dict]:
        """Perform semantic search over candidates."""
        query_embedding = await self.embed_text(query, input_type="query")

        scored = []
        for candidate in candidates:
            if "embedding" in candidate:
                similarity = cosine_similarity(
                    query_embedding,
                    candidate["embedding"],
                )
                scored.append({**candidate, "similarity": similarity})

        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]

    def get_call_count(self) -> int:
        """Get number of embedding calls."""
        return len(self._call_history)

    def reset(self):
        """Reset all state."""
        self._text_embeddings.clear()
        self._call_history.clear()


def create_similar_embeddings(
    base_text: str, similar_texts: list[str]
) -> dict[str, list[float]]:
    """Create embeddings where similar_texts have high similarity to base_text.

    Returns a dict mapping text to embedding vectors.
    """
    # Create base embedding
    base_embedding = [0.5] * 2048

    # Create similar embeddings with small variations
    result = {base_text: base_embedding}

    for i, text in enumerate(similar_texts):
        # Add small random-ish variation to maintain high similarity
        variation = [(0.01 * ((i + j) % 10)) for j in range(2048)]
        similar_embedding = [b + v for b, v in zip(base_embedding, variation)]
        result[text] = similar_embedding

    return result


def create_dissimilar_embeddings(texts: list[str]) -> dict[str, list[float]]:
    """Create embeddings where texts have low similarity to each other.

    Returns a dict mapping text to embedding vectors.
    """
    result = {}

    for i, text in enumerate(texts):
        # Create orthogonal-ish embeddings
        embedding = [0.0] * 2048
        # Set different regions to high values for each text
        start = (i * 200) % 2048
        for j in range(200):
            embedding[(start + j) % 2048] = 1.0
        result[text] = embedding

    return result
