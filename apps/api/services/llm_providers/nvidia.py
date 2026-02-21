"""NVIDIA NIM API provider — wraps existing OpenAI-compatible client."""

from typing import AsyncIterator

from openai import AsyncOpenAI

from config import get_settings
from services.llm_providers.base import BaseEmbeddingProvider, BaseLLMProvider
from utils.logging import get_logger

logger = get_logger(__name__)


class NvidiaLLMProvider(BaseLLMProvider):
    """LLM provider using NVIDIA NIM API (OpenAI-compatible)."""

    def __init__(self, model: str | None = None):
        settings = get_settings()
        self.client = AsyncOpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=settings.get_nvidia_api_key(),
        )
        self._model = model or settings.nvidia_model

    @property
    def model_name(self) -> str:
        return self._model

    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.6,
        max_tokens: int = 4096,
    ) -> tuple[str, dict]:
        response = await self.client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            top_p=0.95,
            max_tokens=max_tokens,
            frequency_penalty=0,
            presence_penalty=0,
        )

        content = response.choices[0].message.content or ""
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens or 0,
                "completion_tokens": response.usage.completion_tokens or 0,
                "total_tokens": response.usage.total_tokens or 0,
            }

        return content, usage

    async def generate_stream(
        self,
        messages: list[dict],
        temperature: float = 0.6,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        stream = await self.client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            top_p=0.95,
            max_tokens=max_tokens,
            frequency_penalty=0,
            presence_penalty=0,
            stream=True,
            stream_options={"include_usage": True},
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content


class NvidiaEmbeddingProvider(BaseEmbeddingProvider):
    """Embedding provider using NVIDIA NV-EmbedQA (OpenAI-compatible)."""

    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(
            api_key=settings.get_nvidia_embedding_api_key(),
            base_url="https://integrate.api.nvidia.com/v1",
        )
        self._model = "nvidia/llama-3.2-nv-embedqa-1b-v2"
        self._dimensions = 2048

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(
        self,
        texts: list[str],
        input_type: str = "passage",
    ) -> list[list[float]]:
        response = await self.client.embeddings.create(
            input=texts,
            model=self._model,
            encoding_format="float",
            extra_body={"input_type": input_type, "truncate": "END"},
        )
        return [item.embedding for item in response.data]
