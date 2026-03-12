"""Gemini LLM provider using google-genai SDK."""

import os
from collections.abc import AsyncIterator

import structlog

from conductor.agents.llm_provider import ChatMessage, LLMProvider
from conductor.core.models import LLMProviderConfig

logger = structlog.get_logger()


class GeminiProvider(LLMProvider):
    """Google Gemini provider via google-genai SDK.

    API key is resolved from:
        1. GEMINI_API_KEY environment variable
        2. config.api_key field (fallback)
    """

    def __init__(self, config: LLMProviderConfig) -> None:
        super().__init__(config)
        self._api_key = os.environ.get("GEMINI_API_KEY") or config.api_key
        self._client = None

    def _get_client(self):
        """Lazy-init the Gemini client."""
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._get_api_key())
        return self._client

    def _to_genai_contents(self, messages: list[ChatMessage]) -> tuple[str | None, list[dict]]:
        """Convert ChatMessage list to Gemini's content format.

        Returns:
            (system_instruction, contents) where contents is a list of
            {"role": "user"|"model", "parts": [{"text": ...}]} dicts.
        """
        system_instruction = None
        contents = []
        for msg in messages:
            if msg.role == "system":
                system_instruction = msg.content
            else:
                role = "model" if msg.role == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": msg.content}]})
        return system_instruction, contents

    async def generate(self, messages: list[ChatMessage], **kwargs) -> str:
        client = self._get_client()
        resolved = self._resolve_kwargs(kwargs)
        system_instruction, contents = self._to_genai_contents(messages)

        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=resolved["temperature"],
            max_output_tokens=resolved["max_tokens"],
            system_instruction=system_instruction,
        )

        response = await client.aio.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )

        text = response.text or ""
        logger.debug("gemini.generate", model=self.model, input_messages=len(messages), output_len=len(text))
        return text

    async def stream(self, messages: list[ChatMessage], **kwargs) -> AsyncIterator[str]:
        client = self._get_client()
        resolved = self._resolve_kwargs(kwargs)
        system_instruction, contents = self._to_genai_contents(messages)

        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=resolved["temperature"],
            max_output_tokens=resolved["max_tokens"],
            system_instruction=system_instruction,
        )

        async for chunk in await client.aio.models.generate_content_stream(
            model=self.model,
            contents=contents,
            config=config,
        ):
            if chunk.text:
                yield chunk.text

    async def is_available(self) -> bool:
        try:
            api_key = self._get_api_key()
            return bool(api_key)
        except ValueError:
            return False
