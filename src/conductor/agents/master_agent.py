"""Master Agent — user-facing LLM with automatic failover.

Phase 3 (MVP): Accept messages → call LLM → return streaming response.
Phase 3b (TODO): Task classification (P0/P1/P2), conversation summarization, memory updates.
"""

from collections.abc import AsyncIterator

import structlog

from conductor.agents.llm_provider import ChatMessage, LLMProvider

logger = structlog.get_logger()

SYSTEM_PROMPT = """\
You are the Master Agent of Code Conductor, an AI orchestration system that coordinates \
multiple Claude Code Workers to complete software engineering tasks.

Your responsibilities:
- Understand user requests and provide helpful responses
- When the user describes a coding task, acknowledge it and provide your assessment

Keep responses concise and focused. Use the user's language (Chinese or English) to respond.\
"""


class MasterAgent:
    """Orchestrates user interaction through a primary LLM with automatic fallback.

    Usage:
        agent = MasterAgent(primary=gemini_provider, fallback=kimi_provider)
        async for token in agent.chat(session_history, user_message):
            print(token, end="")
    """

    def __init__(self, primary: LLMProvider, fallback: LLMProvider | None = None) -> None:
        self.primary = primary
        self.fallback = fallback
        self._active_provider: LLMProvider = primary

    @property
    def active_provider_name(self) -> str:
        return self._active_provider.provider_name

    async def chat(self, history: list[ChatMessage], user_message: str, **kwargs) -> AsyncIterator[str]:
        """Stream a response to the user's message with automatic failover.

        Args:
            history: Previous conversation messages.
            user_message: The new user input.
            **kwargs: Provider-specific overrides.

        Yields:
            Response text chunks.
        """
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            *history,
            ChatMessage(role="user", content=user_message),
        ]

        try:
            async for chunk in self._active_provider.stream(messages, **kwargs):
                yield chunk
        except Exception as primary_err:
            if self.fallback is None or self._active_provider is self.fallback:
                logger.error("master_agent.no_fallback", error=str(primary_err))
                raise

            logger.warning(
                "master_agent.failover",
                from_provider=self._active_provider.provider_name,
                to_provider=self.fallback.provider_name,
                error=str(primary_err),
            )
            self._active_provider = self.fallback

            try:
                async for chunk in self.fallback.stream(messages, **kwargs):
                    yield chunk
            except Exception as fallback_err:
                logger.error(
                    "master_agent.all_providers_failed",
                    primary_error=str(primary_err),
                    fallback_error=str(fallback_err),
                )
                raise

    async def generate(self, history: list[ChatMessage], user_message: str, **kwargs) -> str:
        """Non-streaming version of chat. Returns complete response text."""
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            *history,
            ChatMessage(role="user", content=user_message),
        ]

        try:
            return await self._active_provider.generate(messages, **kwargs)
        except Exception as primary_err:
            if self.fallback is None or self._active_provider is self.fallback:
                raise

            logger.warning(
                "master_agent.failover",
                from_provider=self._active_provider.provider_name,
                to_provider=self.fallback.provider_name,
                error=str(primary_err),
            )
            self._active_provider = self.fallback
            return await self.fallback.generate(messages, **kwargs)

    def reset_to_primary(self) -> None:
        """Reset active provider back to primary (e.g., after transient failure resolves)."""
        if self._active_provider is not self.primary:
            logger.info("master_agent.reset_to_primary", from_provider=self._active_provider.provider_name)
            self._active_provider = self.primary
