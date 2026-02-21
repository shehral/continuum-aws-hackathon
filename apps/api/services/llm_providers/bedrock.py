"""Amazon Bedrock provider — Claude via Converse API.

Uses boto3 bedrock-runtime client with asyncio.to_thread() for async compatibility.
Requires AWS credentials configured (env vars, ~/.aws/credentials, or IAM role).
"""

import asyncio
import json
from typing import AsyncIterator

from config import get_settings
from services.llm_providers.base import BaseEmbeddingProvider, BaseLLMProvider
from utils.logging import get_logger

logger = get_logger(__name__)


def _to_bedrock_messages(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    """Convert OpenAI-format messages to Bedrock Converse format.

    Bedrock Converse API expects:
    - system: list of {"text": "..."} (separate param)
    - messages: list of {"role": "user"|"assistant", "content": [{"text": "..."}]}

    Returns:
        Tuple of (system_prompts, messages) in Bedrock format.
    """
    system_prompts = []
    bedrock_messages = []

    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")

        if role == "system":
            system_prompts.append({"text": content})
        else:
            bedrock_messages.append({
                "role": role,
                "content": [{"text": content}],
            })

    return system_prompts, bedrock_messages


class BedrockLLMProvider(BaseLLMProvider):
    """LLM provider using Amazon Bedrock Converse API."""

    def __init__(self):
        settings = get_settings()
        self._model_id = settings.bedrock_model_id
        self._region = settings.aws_region

        # Lazy-initialize boto3 client (import is heavy)
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self._region,
            )
        return self._client

    @property
    def model_name(self) -> str:
        return self._model_id

    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.6,
        max_tokens: int = 4096,
    ) -> tuple[str, dict]:
        system_prompts, bedrock_messages = _to_bedrock_messages(messages)

        kwargs = {
            "modelId": self._model_id,
            "messages": bedrock_messages,
            "inferenceConfig": {
                "temperature": temperature,
                "maxTokens": max_tokens,
                "topP": 0.95,
            },
        }
        if system_prompts:
            kwargs["system"] = system_prompts

        # boto3 is synchronous — run in thread pool
        client = self._get_client()
        response = await asyncio.to_thread(client.converse, **kwargs)

        # Extract text from response
        output = response.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", [])
        text = ""
        for block in content_blocks:
            if "text" in block:
                text += block["text"]

        # Extract usage
        usage_info = response.get("usage", {})
        usage = {
            "prompt_tokens": usage_info.get("inputTokens", 0),
            "completion_tokens": usage_info.get("outputTokens", 0),
            "total_tokens": usage_info.get("totalTokens", 0),
        }

        return text, usage

    async def generate_stream(
        self,
        messages: list[dict],
        temperature: float = 0.6,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        system_prompts, bedrock_messages = _to_bedrock_messages(messages)

        kwargs = {
            "modelId": self._model_id,
            "messages": bedrock_messages,
            "inferenceConfig": {
                "temperature": temperature,
                "maxTokens": max_tokens,
                "topP": 0.95,
            },
        }
        if system_prompts:
            kwargs["system"] = system_prompts

        # Start the stream in a thread (boto3 is sync)
        client = self._get_client()
        response = await asyncio.to_thread(client.converse_stream, **kwargs)

        # Process the event stream
        stream = response.get("stream")
        if stream is None:
            return

        # Iterate the event stream — each event is sync, wrap in to_thread
        for event in stream:
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"].get("delta", {})
                text = delta.get("text", "")
                if text:
                    yield text


class BedrockEmbeddingProvider(BaseEmbeddingProvider):
    """Embedding provider using Amazon Titan Embeddings V2.

    Note: Titan produces 1024-dim embeddings vs NVIDIA's 2048-dim.
    Switching providers requires re-indexing Neo4j vector data.
    For the hackathon, we recommend keeping NVIDIA embeddings.
    """

    def __init__(self):
        settings = get_settings()
        self._model_id = settings.bedrock_embedding_model_id
        self._region = settings.aws_region
        self._dimensions = 1024  # Titan V2 default
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self._region,
            )
        return self._client

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(
        self,
        texts: list[str],
        input_type: str = "passage",
    ) -> list[list[float]]:
        client = self._get_client()
        results = []

        # Titan embedding API processes one text at a time
        for text in texts:
            body = json.dumps({
                "inputText": text,
                "dimensions": self._dimensions,
            })
            response = await asyncio.to_thread(
                client.invoke_model,
                modelId=self._model_id,
                body=body,
                contentType="application/json",
                accept="application/json",
            )
            response_body = json.loads(response["body"].read())
            results.append(response_body["embedding"])

        return results
