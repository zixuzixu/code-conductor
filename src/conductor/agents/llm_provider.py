"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from conductor.core.models import LLMProviderConfig


@dataclass
class ChatMessage:
    """A single message in a conversation."""

    role: str  # "system", "user", "assistant"
    content: str


class LLMProvider(ABC):
    """Abstract LLM provider — all model integrations implement this interface.

    Subclasses must implement:
        - generate(): single-shot response
        - stream(): token-by-token async iterator
        - is_available(): health check
    """

    def __init__(self, config: LLMProviderConfig) -> None:
        self.config = config
        self.model = config.model
        self._api_key: str | None = None

    @property
    def provider_name(self) -> str:
        return self.config.provider

    @abstractmethod
    async def generate(self, messages: list[ChatMessage], **kwargs) -> str:
        """Generate a complete response from the model.

        Args:
            messages: Conversation history.
            **kwargs: Provider-specific overrides (temperature, max_tokens, etc.)

        Returns:
            The assistant's response text.
        """

    @abstractmethod
    async def stream(self, messages: list[ChatMessage], **kwargs) -> AsyncIterator[str]:
        """Stream response tokens from the model.

        Args:
            messages: Conversation history.
            **kwargs: Provider-specific overrides.

        Yields:
            Individual text chunks as they arrive.
        """

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this provider is reachable and configured.

        Returns:
            True if the provider can accept requests.
        """

    def _get_api_key(self) -> str:
        """Resolve API key: environment variable first, then config file."""
        if self._api_key:
            return self._api_key
        raise ValueError(f"No API key configured for {self.provider_name}")

    def _resolve_kwargs(self, kwargs: dict) -> dict:
        """Merge per-call overrides with config defaults."""
        defaults = {
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        defaults.update(kwargs)
        return defaults
