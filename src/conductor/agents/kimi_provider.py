"""Kimi k2.5 LLM provider using OpenAI-compatible SDK."""

import os
from collections.abc import AsyncIterator

import structlog

from conductor.agents.llm_provider import ChatMessage, LLMProvider
from conductor.core.models import LLMProviderConfig

logger = structlog.get_logger()

DEFAULT_KIMI_BASE_URL = "https://api.moonshot.cn/v1"


class KimiProvider(LLMProvider):
    """Kimi (Moonshot) provider via OpenAI-compatible API.

    API key is resolved from:
        1. KIMI_API_KEY environment variable
        2. config.api_key field (fallback)
    """

    def __init__(self, config: LLMProviderConfig) -> None:
        super().__init__(config)
        self._api_key = os.environ.get("KIMI_API_KEY") or config.api_key
        self._base_url = config.base_url or DEFAULT_KIMI_BASE_URL
        self._client = None

    def _get_client(self):
        """Lazy-init the OpenAI-compatible async client."""
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=self._get_api_key(),
                base_url=self._base_url,
            )
        return self._client

    def _to_openai_messages(self, messages: list[ChatMessage]) -> list[dict]:
        """Convert ChatMessage list to OpenAI message format."""
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    async def generate(self, messages: list[ChatMessage], **kwargs) -> str:
        client = self._get_client()
        resolved = self._resolve_kwargs(kwargs)
        openai_messages = self._to_openai_messages(messages)

        response = await client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            temperature=resolved["temperature"],
            max_tokens=resolved["max_tokens"],
            stream=False,
        )

        text = response.choices[0].message.content or ""
        logger.debug("kimi.generate", model=self.model, input_messages=len(messages), output_len=len(text))
        return text

    async def stream(self, messages: list[ChatMessage], **kwargs) -> AsyncIterator[str]:
        client = self._get_client()
        resolved = self._resolve_kwargs(kwargs)
        openai_messages = self._to_openai_messages(messages)

        response = await client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            temperature=resolved["temperature"],
            max_tokens=resolved["max_tokens"],
            stream=True,
        )

        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def is_available(self) -> bool:
        try:
            api_key = self._get_api_key()
            return bool(api_key)
        except ValueError:
            return False
