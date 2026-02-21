"""Adapter wrapping Strands Agents SDK models to the BaseLLMProvider interface."""

from typing import AsyncIterator

from services.llm_providers.base import BaseLLMProvider


class StrandsLLMProviderAdapter(BaseLLMProvider):
    """Adapts any Strands SDK Model to the BaseLLMProvider interface.

    Wraps Strands models (BedrockModel, OpenAIModel, etc.) so they can be used
    by LLMClient without changing any consumer code.
    """

    def __init__(self, strands_model, model_id: str, *, use_params_dict: bool = False):
        self._model = strands_model
        self._model_id = model_id
        self._use_params_dict = use_params_dict

    @property
    def model_name(self) -> str:
        return self._model_id

    def _apply_config(self, temperature: float, max_tokens: int) -> None:
        if self._use_params_dict:
            self._model.update_config(params={"temperature": temperature, "max_tokens": max_tokens})
        else:
            self._model.update_config(temperature=temperature, max_tokens=max_tokens)

    def _prepare_messages(
        self, messages: list[dict]
    ) -> tuple[list[dict], str | None]:
        """Convert OpenAI-format messages to Strands format.

        Extracts system messages into a separate system_prompt string.
        Converts remaining messages to Strands content block format.

        Returns:
            (conversation_messages, system_prompt_or_None)
        """
        system_parts = []
        conversation = []
        for msg in messages:
            if msg["role"] == "system":
                system_parts.append(msg["content"])
            else:
                conversation.append({
                    "role": msg["role"],
                    "content": [{"text": msg["content"]}],
                })
        system_prompt = "\n".join(system_parts) if system_parts else None
        return conversation, system_prompt

    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.6,
        max_tokens: int = 4096,
    ) -> tuple[str, dict]:
        conversation, system_prompt = self._prepare_messages(messages)
        self._apply_config(temperature, max_tokens)

        full_text = ""
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        async for event in self._model.stream(
            messages=conversation,
            system_prompt=system_prompt,
        ):
            if "contentBlockDelta" in event:
                text = event["contentBlockDelta"].get("delta", {}).get("text", "")
                if text:
                    full_text += text

            if "metadata" in event:
                u = event["metadata"].get("usage", {})
                usage["prompt_tokens"] = u.get("inputTokens", 0)
                usage["completion_tokens"] = u.get("outputTokens", 0)
                usage["total_tokens"] = u.get("totalTokens", 0)

        return full_text, usage

    async def generate_stream(
        self,
        messages: list[dict],
        temperature: float = 0.6,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        conversation, system_prompt = self._prepare_messages(messages)
        self._apply_config(temperature, max_tokens)

        async for event in self._model.stream(
            messages=conversation,
            system_prompt=system_prompt,
        ):
            if "contentBlockDelta" in event:
                text = event["contentBlockDelta"].get("delta", {}).get("text", "")
                if text:
                    yield text
