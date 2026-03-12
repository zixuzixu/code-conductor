"""Tests for LLM providers and Master Agent.

These tests use mock clients to avoid real API calls.
"""


import pytest

from conductor.agents.gemini_provider import GeminiProvider
from conductor.agents.kimi_provider import KimiProvider
from conductor.agents.llm_provider import ChatMessage, LLMProvider
from conductor.agents.master_agent import MasterAgent
from conductor.core.models import LLMProviderConfig

# --- LLMProvider ABC ---


def test_llm_provider_is_abstract():
    """Cannot instantiate LLMProvider directly."""
    config = LLMProviderConfig(provider="test", model="test-model")
    with pytest.raises(TypeError):
        LLMProvider(config)


# --- GeminiProvider ---


def test_gemini_api_key_from_env(monkeypatch):
    """Gemini resolves API key from GEMINI_API_KEY env var."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    config = LLMProviderConfig(provider="gemini", model="gemini-3.1-pro-preview")
    provider = GeminiProvider(config)
    assert provider._get_api_key() == "test-gemini-key"


def test_gemini_api_key_from_config(monkeypatch):
    """Gemini falls back to config.api_key when env var is absent."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    config = LLMProviderConfig(provider="gemini", model="gemini-3.1-pro-preview", api_key="config-key")
    provider = GeminiProvider(config)
    assert provider._get_api_key() == "config-key"


def test_gemini_no_api_key_raises(monkeypatch):
    """Gemini raises ValueError when no API key is available."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    config = LLMProviderConfig(provider="gemini", model="gemini-3.1-pro-preview", api_key="")
    provider = GeminiProvider(config)
    with pytest.raises(ValueError, match="No API key"):
        provider._get_api_key()


def test_gemini_content_conversion():
    """Gemini correctly converts ChatMessage to genai format."""
    config = LLMProviderConfig(provider="gemini", model="test")
    provider = GeminiProvider(config)
    messages = [
        ChatMessage(role="system", content="You are helpful."),
        ChatMessage(role="user", content="Hello"),
        ChatMessage(role="assistant", content="Hi!"),
        ChatMessage(role="user", content="How are you?"),
    ]
    system, contents = provider._to_genai_contents(messages)
    assert system == "You are helpful."
    assert len(contents) == 3
    assert contents[0]["role"] == "user"
    assert contents[1]["role"] == "model"  # assistant → model
    assert contents[2]["role"] == "user"


async def test_gemini_is_available(monkeypatch):
    """Gemini is_available returns True when API key exists."""
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    config = LLMProviderConfig(provider="gemini", model="test")
    provider = GeminiProvider(config)
    assert await provider.is_available() is True


async def test_gemini_is_unavailable(monkeypatch):
    """Gemini is_available returns False when no API key."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    config = LLMProviderConfig(provider="gemini", model="test", api_key="")
    provider = GeminiProvider(config)
    assert await provider.is_available() is False


# --- KimiProvider ---


def test_kimi_api_key_from_env(monkeypatch):
    """Kimi resolves API key from KIMI_API_KEY env var."""
    monkeypatch.setenv("KIMI_API_KEY", "test-kimi-key")
    config = LLMProviderConfig(provider="kimi", model="kimi-k2.5")
    provider = KimiProvider(config)
    assert provider._get_api_key() == "test-kimi-key"


def test_kimi_default_base_url():
    """Kimi uses Moonshot base URL by default."""
    config = LLMProviderConfig(provider="kimi", model="kimi-k2.5")
    provider = KimiProvider(config)
    assert provider._base_url == "https://api.moonshot.cn/v1"


def test_kimi_custom_base_url():
    """Kimi accepts custom base URL from config."""
    config = LLMProviderConfig(provider="kimi", model="kimi-k2.5", base_url="https://custom.api.com/v1")
    provider = KimiProvider(config)
    assert provider._base_url == "https://custom.api.com/v1"


def test_kimi_message_conversion():
    """Kimi correctly converts ChatMessage to OpenAI format."""
    config = LLMProviderConfig(provider="kimi", model="test")
    provider = KimiProvider(config)
    messages = [
        ChatMessage(role="system", content="System msg"),
        ChatMessage(role="user", content="User msg"),
    ]
    result = provider._to_openai_messages(messages)
    assert result == [
        {"role": "system", "content": "System msg"},
        {"role": "user", "content": "User msg"},
    ]


# --- MasterAgent ---


def _make_provider(name: str, stream_chunks: list[str] | None = None, generate_text: str = "response") -> LLMProvider:
    """Create a mock LLMProvider."""
    config = LLMProviderConfig(provider=name, model=f"{name}-model", api_key="fake-key")

    class MockProvider(LLMProvider):
        async def generate(self, messages, **kwargs):
            return generate_text

        async def stream(self, messages, **kwargs):
            for chunk in (stream_chunks or ["Hello", " World"]):
                yield chunk

        async def is_available(self):
            return True

    return MockProvider(config)


def _make_failing_provider(name: str, error_msg: str = "API Error") -> LLMProvider:
    """Create a provider that always raises."""
    config = LLMProviderConfig(provider=name, model=f"{name}-model", api_key="fake-key")

    class FailingProvider(LLMProvider):
        async def generate(self, messages, **kwargs):
            raise RuntimeError(error_msg)

        async def stream(self, messages, **kwargs):
            raise RuntimeError(error_msg)
            yield  # unreachable, but makes this an async generator

        async def is_available(self):
            return False

    return FailingProvider(config)


async def test_master_agent_stream():
    """MasterAgent streams response from primary provider."""
    primary = _make_provider("primary", stream_chunks=["Hello", " ", "World"])
    agent = MasterAgent(primary=primary)

    chunks = []
    async for chunk in agent.chat([], "Hi"):
        chunks.append(chunk)

    assert chunks == ["Hello", " ", "World"]
    assert agent.active_provider_name == "primary"


async def test_master_agent_generate():
    """MasterAgent generate returns complete response."""
    primary = _make_provider("primary", generate_text="Complete response")
    agent = MasterAgent(primary=primary)

    result = await agent.generate([], "Hi")
    assert result == "Complete response"


async def test_master_agent_failover_stream():
    """MasterAgent falls over to fallback when primary fails during streaming."""
    primary = _make_failing_provider("primary")
    fallback = _make_provider("fallback", stream_chunks=["Fallback", " response"])
    agent = MasterAgent(primary=primary, fallback=fallback)

    chunks = []
    async for chunk in agent.chat([], "Hi"):
        chunks.append(chunk)

    assert chunks == ["Fallback", " response"]
    assert agent.active_provider_name == "fallback"


async def test_master_agent_failover_generate():
    """MasterAgent falls over to fallback when primary fails during generate."""
    primary = _make_failing_provider("primary")
    fallback = _make_provider("fallback", generate_text="Fallback text")
    agent = MasterAgent(primary=primary, fallback=fallback)

    result = await agent.generate([], "Hi")
    assert result == "Fallback text"
    assert agent.active_provider_name == "fallback"


async def test_master_agent_both_fail():
    """MasterAgent raises when both providers fail."""
    primary = _make_failing_provider("primary", "Primary down")
    fallback = _make_failing_provider("fallback", "Fallback down")
    agent = MasterAgent(primary=primary, fallback=fallback)

    with pytest.raises(RuntimeError, match="Fallback down"):
        async for _ in agent.chat([], "Hi"):
            pass


async def test_master_agent_no_fallback_raises():
    """MasterAgent raises immediately when no fallback is configured."""
    primary = _make_failing_provider("primary")
    agent = MasterAgent(primary=primary, fallback=None)

    with pytest.raises(RuntimeError):
        async for _ in agent.chat([], "Hi"):
            pass


async def test_master_agent_reset_to_primary():
    """MasterAgent can reset back to primary provider."""
    primary = _make_provider("primary")
    fallback = _make_provider("fallback")
    agent = MasterAgent(primary=primary, fallback=fallback)

    # Simulate failover
    agent._active_provider = fallback
    assert agent.active_provider_name == "fallback"

    agent.reset_to_primary()
    assert agent.active_provider_name == "primary"


async def test_master_agent_preserves_history():
    """MasterAgent passes conversation history to provider."""
    history = [
        ChatMessage(role="user", content="What is 2+2?"),
        ChatMessage(role="assistant", content="4"),
    ]

    class RecordingProvider(LLMProvider):
        def __init__(self):
            config = LLMProviderConfig(provider="recorder", model="test", api_key="key")
            super().__init__(config)
            self.received_messages = []

        async def generate(self, messages, **kwargs):
            self.received_messages = messages
            return "ok"

        async def stream(self, messages, **kwargs):
            self.received_messages = messages
            yield "ok"

        async def is_available(self):
            return True

    provider = RecordingProvider()
    agent = MasterAgent(primary=provider)
    await agent.generate(history, "Follow up")

    # system + 2 history + 1 new user message = 4
    assert len(provider.received_messages) == 4
    assert provider.received_messages[0].role == "system"
    assert provider.received_messages[-1].content == "Follow up"
