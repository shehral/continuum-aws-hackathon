"""Abstract base classes for LLM and Embedding providers."""

from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseLLMProvider(ABC):
    """Abstract base for LLM providers (NVIDIA NIM, Amazon Bedrock, etc.)."""

    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.6,
        max_tokens: int = 4096,
    ) -> tuple[str, dict]:
        """Generate a completion.

        Args:
            messages: List of {"role": "...", "content": "..."} dicts.
            temperature: Sampling temperature.
            max_tokens: Max tokens to generate.

        Returns:
            Tuple of (generated_text, usage_dict).
            usage_dict should contain: {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
        """
        ...

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[dict],
        temperature: float = 0.6,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Generate a streaming completion.

        Args:
            messages: List of message dicts.
            temperature: Sampling temperature.
            max_tokens: Max tokens to generate.

        Yields:
            Text chunks as they are generated.
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier for logging."""
        ...


class BaseEmbeddingProvider(ABC):
    """Abstract base for embedding providers."""

    @abstractmethod
    async def embed(
        self,
        texts: list[str],
        input_type: str = "passage",
    ) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Args:
            texts: Texts to embed.
            input_type: "query" for search queries, "passage" for documents.

        Returns:
            List of embedding vectors.
        """
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the embedding dimensionality."""
        ...
