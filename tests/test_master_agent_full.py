"""Tests for Master Agent Phase 3b features.

Covers: task classification, conversation summarization, memory updates, worker result review.
"""

import json

import pytest

from conductor.agents.llm_provider import ChatMessage, LLMProvider
from conductor.agents.master_agent import (
    MasterAgent,
    _parse_llm_json,
    extract_memory_updates,
)
from conductor.core.models import LLMProviderConfig

# --- Helpers ---


def _make_provider(
    name: str = "test",
    generate_text: str = "response",
    stream_chunks: list[str] | None = None,
) -> LLMProvider:
    """Create a mock LLMProvider that returns predictable output."""
    config = LLMProviderConfig(provider=name, model=f"{name}-model", api_key="fake")

    class MockProvider(LLMProvider):
        async def generate(self, messages, **kwargs):
            return generate_text

        async def stream(self, messages, **kwargs):
            for chunk in (stream_chunks or ["Hello", " World"]):
                yield chunk

        async def is_available(self):
            return True

    return MockProvider(config)


def _make_failing_provider(name: str = "fail", error_msg: str = "API Error") -> LLMProvider:
    config = LLMProviderConfig(provider=name, model=f"{name}-model", api_key="fake")

    class FailingProvider(LLMProvider):
        async def generate(self, messages, **kwargs):
            raise RuntimeError(error_msg)

        async def stream(self, messages, **kwargs):
            raise RuntimeError(error_msg)
            yield  # makes this an async generator

        async def is_available(self):
            return False

    return FailingProvider(config)


# --- _parse_llm_json ---


class TestParseLlmJson:
    def test_plain_json_array(self):
        result = _parse_llm_json('[{"title": "fix bug", "priority": "p0"}]')
        assert result == [{"title": "fix bug", "priority": "p0"}]

    def test_json_with_markdown_fences(self):
        text = '```json\n[{"title": "task"}]\n```'
        result = _parse_llm_json(text)
        assert result == [{"title": "task"}]

    def test_json_with_plain_fences(self):
        text = '```\n{"key": "value"}\n```'
        result = _parse_llm_json(text)
        assert result == {"key": "value"}

    def test_json_object(self):
        result = _parse_llm_json('{"verdict": "accept"}')
        assert result == {"verdict": "accept"}

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_llm_json("not json at all")


# --- extract_memory_updates ---


class TestExtractMemoryUpdates:
    def test_no_updates(self):
        text = "Just a normal response with no memory tags."
        cleaned, updates = extract_memory_updates(text)
        assert cleaned == text
        assert updates == []

    def test_single_update(self):
        text = 'Hello [MEMORY_UPDATE]{"key": "lang", "value": "python"}[/MEMORY_UPDATE] world'
        cleaned, updates = extract_memory_updates(text)
        assert "MEMORY_UPDATE" not in cleaned
        assert "Hello" in cleaned
        assert "world" in cleaned
        assert len(updates) == 1
        assert updates[0] == {"key": "lang", "value": "python"}

    def test_multiple_updates(self):
        text = (
            '[MEMORY_UPDATE]{"key": "a", "value": "1"}[/MEMORY_UPDATE] mid '
            '[MEMORY_UPDATE]{"key": "b", "value": "2"}[/MEMORY_UPDATE]'
        )
        _cleaned, updates = extract_memory_updates(text)
        assert len(updates) == 2
        assert updates[0]["key"] == "a"
        assert updates[1]["key"] == "b"

    def test_invalid_json_skipped(self):
        text = "[MEMORY_UPDATE]not valid json[/MEMORY_UPDATE] after"
        _cleaned, updates = extract_memory_updates(text)
        assert updates == []
        assert "after" in _cleaned

    def test_non_dict_skipped(self):
        text = '[MEMORY_UPDATE]["just", "an", "array"][/MEMORY_UPDATE] rest'
        _cleaned, updates = extract_memory_updates(text)
        assert updates == []


# --- classify_task ---


class TestClassifyTask:
    async def test_basic_classification(self):
        llm_response = json.dumps([
            {"title": "Fix login crash", "description": "Login page crashes on submit", "priority": "p0"},
            {"title": "Add dark mode", "description": "Implement dark mode toggle", "priority": "p1"},
        ])
        provider = _make_provider(generate_text=llm_response)
        agent = MasterAgent(primary=provider)

        tasks = await agent.classify_task("Fix the login crash and add dark mode")
        assert len(tasks) == 2
        assert tasks[0]["priority"] == "p0"
        assert tasks[1]["priority"] == "p1"

    async def test_classification_with_markdown_fences(self):
        llm_response = '```json\n[{"title": "Update docs", "description": "Fix README", "priority": "p2"}]\n```'
        provider = _make_provider(generate_text=llm_response)
        agent = MasterAgent(primary=provider)

        tasks = await agent.classify_task("Update the README")
        assert len(tasks) == 1
        assert tasks[0]["priority"] == "p2"

    async def test_classification_invalid_json_fallback(self):
        provider = _make_provider(generate_text="I can't parse this as JSON, sorry!")
        agent = MasterAgent(primary=provider)

        tasks = await agent.classify_task("Fix a bug")
        assert len(tasks) == 1
        assert tasks[0]["priority"] == "p1"
        assert tasks[0]["title"] == "Fix a bug"

    async def test_classification_normalizes_priority(self):
        llm_response = json.dumps([{"title": "Task", "description": "Desc", "priority": "P0"}])
        provider = _make_provider(generate_text=llm_response)
        agent = MasterAgent(primary=provider)

        tasks = await agent.classify_task("something")
        assert tasks[0]["priority"] == "p0"

    async def test_classification_invalid_priority_defaults_p1(self):
        llm_response = json.dumps([{"title": "Task", "description": "Desc", "priority": "critical"}])
        provider = _make_provider(generate_text=llm_response)
        agent = MasterAgent(primary=provider)

        tasks = await agent.classify_task("something")
        assert tasks[0]["priority"] == "p1"

    async def test_classification_single_object_wrapped(self):
        """LLM returns a single object instead of array — should be wrapped."""
        llm_response = json.dumps({"title": "Solo task", "description": "Just one", "priority": "p1"})
        provider = _make_provider(generate_text=llm_response)
        agent = MasterAgent(primary=provider)

        tasks = await agent.classify_task("do something")
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Solo task"

    async def test_classification_failover(self):
        primary = _make_failing_provider("primary")
        fallback_response = json.dumps([{"title": "Task", "description": "Desc", "priority": "p1"}])
        fallback = _make_provider("fallback", generate_text=fallback_response)
        agent = MasterAgent(primary=primary, fallback=fallback)

        tasks = await agent.classify_task("do work")
        assert len(tasks) == 1
        assert agent.active_provider_name == "fallback"


# --- summarize_conversation ---


class TestSummarizeConversation:
    def test_short_conversation_unchanged(self):
        messages = [ChatMessage(role="user", content=f"msg {i}") for i in range(8)]
        agent = MasterAgent(primary=_make_provider())

        result = agent.summarize_conversation(messages)
        assert result is messages  # same object, no copy
        assert len(result) == 8

    def test_exactly_ten_unchanged(self):
        messages = [ChatMessage(role="user", content=f"msg {i}") for i in range(10)]
        agent = MasterAgent(primary=_make_provider())

        result = agent.summarize_conversation(messages)
        assert result is messages

    def test_eleven_messages_compressed(self):
        messages = [
            ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"message number {i}")
            for i in range(11)
        ]
        agent = MasterAgent(primary=_make_provider())

        result = agent.summarize_conversation(messages)
        # 1 summary + 6 recent = 7
        assert len(result) == 7
        assert result[0].role == "system"
        assert "Summary of earlier conversation" in result[0].content
        # Recent 6 preserved
        assert result[1].content == "message number 5"
        assert result[-1].content == "message number 10"

    def test_summary_contains_old_messages(self):
        messages = [ChatMessage(role="user", content=f"topic_{i}") for i in range(12)]
        agent = MasterAgent(primary=_make_provider())

        result = agent.summarize_conversation(messages)
        summary = result[0].content
        # Old messages (0..5) should appear in summary
        assert "topic_0" in summary
        assert "topic_5" in summary
        # Recent messages (6..11) should NOT appear in summary
        assert "topic_6" not in summary

    def test_long_message_truncated_in_summary(self):
        long_content = "x" * 300
        messages = [ChatMessage(role="user", content=long_content)] + [
            ChatMessage(role="user", content=f"m{i}") for i in range(10)
        ]
        agent = MasterAgent(primary=_make_provider())

        result = agent.summarize_conversation(messages)
        summary = result[0].content
        # The 300-char message should be truncated to 200 + "..."
        assert "..." in summary
        assert "x" * 201 not in summary


# --- Memory updates in chat/generate ---


class TestMemoryUpdatesIntegration:
    async def test_generate_extracts_memory(self):
        response_with_memory = (
            'Here is info. [MEMORY_UPDATE]{"key": "pref", "value": "dark mode"}[/MEMORY_UPDATE] Done.'
        )
        provider = _make_provider(generate_text=response_with_memory)
        agent = MasterAgent(primary=provider)

        result = await agent.generate([], "test")
        assert "MEMORY_UPDATE" not in result
        assert "Here is info." in result
        assert len(agent.memory_updates) == 1
        assert agent.memory_updates[0]["key"] == "pref"

    async def test_generate_no_memory(self):
        provider = _make_provider(generate_text="Just a normal response")
        agent = MasterAgent(primary=provider)

        result = await agent.generate([], "test")
        assert result == "Just a normal response"
        assert agent.memory_updates == []

    async def test_chat_extracts_memory(self):
        chunks = [
            "Start ",
            '[MEMORY_UPDATE]{"key": "x", "value": "y"}[/MEMORY_UPDATE]',
            " end",
        ]
        provider = _make_provider(stream_chunks=chunks)
        agent = MasterAgent(primary=provider)

        collected = []
        async for chunk in agent.chat([], "test"):
            collected.append(chunk)

        assert len(agent.memory_updates) == 1
        assert agent.memory_updates[0]["key"] == "x"

    async def test_memory_updates_accumulate(self):
        resp1 = 'A [MEMORY_UPDATE]{"key": "a", "value": "1"}[/MEMORY_UPDATE]'
        resp2 = 'B [MEMORY_UPDATE]{"key": "b", "value": "2"}[/MEMORY_UPDATE]'
        provider1 = _make_provider(generate_text=resp1)
        agent = MasterAgent(primary=provider1)

        await agent.generate([], "first")
        # Swap provider to return different response
        agent.primary = _make_provider(generate_text=resp2)
        agent._active_provider = agent.primary
        await agent.generate([], "second")

        assert len(agent.memory_updates) == 2


# --- review_worker_result ---


class TestReviewWorkerResult:
    async def test_accept_verdict(self):
        review_response = json.dumps({
            "verdict": "accept",
            "feedback": "Task completed successfully.",
            "suggestions": [],
        })
        provider = _make_provider(generate_text=review_response)
        agent = MasterAgent(primary=provider)

        result = await agent.review_worker_result(
            task={"title": "Fix bug", "description": "Fix the login bug"},
            result={"exit_code": 0, "summary": "Fixed the bug"},
        )
        assert result["verdict"] == "accept"
        assert result["feedback"] == "Task completed successfully."
        assert result["suggestions"] == []

    async def test_reject_verdict_with_suggestions(self):
        review_response = json.dumps({
            "verdict": "reject",
            "feedback": "The fix introduces a regression.",
            "suggestions": ["Add unit tests", "Check edge cases"],
        })
        provider = _make_provider(generate_text=review_response)
        agent = MasterAgent(primary=provider)

        result = await agent.review_worker_result(
            task={"title": "Refactor auth", "description": "Refactor authentication module"},
            result={"exit_code": 1, "summary": "Partial refactor done"},
        )
        assert result["verdict"] == "reject"
        assert len(result["suggestions"]) == 2

    async def test_review_with_markdown_fences(self):
        review_response = (
            '```json\n{"verdict": "partial", "feedback": "Needs work", "suggestions": ["Do more"]}\n```'
        )
        provider = _make_provider(generate_text=review_response)
        agent = MasterAgent(primary=provider)

        result = await agent.review_worker_result(
            task={"title": "T", "description": "D"},
            result={"exit_code": 0},
        )
        assert result["verdict"] == "partial"

    async def test_review_invalid_json_fallback(self):
        provider = _make_provider(generate_text="I cannot review this properly")
        agent = MasterAgent(primary=provider)

        result = await agent.review_worker_result(
            task={"title": "T", "description": "D"},
            result={},
        )
        assert result["verdict"] == "partial"
        assert "Failed to parse" in result["feedback"]

    async def test_review_invalid_verdict_normalized(self):
        review_response = json.dumps({
            "verdict": "maybe",
            "feedback": "Unsure",
            "suggestions": [],
        })
        provider = _make_provider(generate_text=review_response)
        agent = MasterAgent(primary=provider)

        result = await agent.review_worker_result(
            task={"title": "T", "description": "D"},
            result={},
        )
        assert result["verdict"] == "partial"

    async def test_review_missing_keys_filled(self):
        review_response = json.dumps({"verdict": "accept"})
        provider = _make_provider(generate_text=review_response)
        agent = MasterAgent(primary=provider)

        result = await agent.review_worker_result(
            task={"title": "T", "description": "D"},
            result={},
        )
        assert result["verdict"] == "accept"
        assert "feedback" in result
        assert "suggestions" in result

    async def test_review_failover(self):
        primary = _make_failing_provider("primary")
        review_response = json.dumps({
            "verdict": "accept", "feedback": "Good", "suggestions": [],
        })
        fallback = _make_provider("fallback", generate_text=review_response)
        agent = MasterAgent(primary=primary, fallback=fallback)

        result = await agent.review_worker_result(
            task={"title": "T", "description": "D"},
            result={},
        )
        assert result["verdict"] == "accept"
        assert agent.active_provider_name == "fallback"
