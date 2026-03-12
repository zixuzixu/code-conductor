"""Master Agent — user-facing LLM with automatic failover.

Phase 3 (MVP): Accept messages → call LLM → return streaming response.
Phase 3b: Task classification (P0/P1/P2), conversation summarization, memory updates, worker review.
"""

import json
import re
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

When you learn something important about the user's project, preferences, or constraints that should be \
remembered across sessions, wrap it in memory update tags like this:
[MEMORY_UPDATE]{"key": "short_identifier", "value": "what to remember"}[/MEMORY_UPDATE]

Keep responses concise and focused. Use the user's language (Chinese or English) to respond.\
"""

CLASSIFY_SYSTEM_PROMPT = """\
You are a task classifier for a software engineering orchestration system.

Given a user message, extract one or more discrete tasks and classify each by priority:
- p0: Urgent bugs, security vulnerabilities, production incidents, data loss risks
- p1: Feature requests, improvements, non-critical bug fixes, refactoring with functional impact
- p2: Documentation updates, code cleanup, style fixes, minor refactoring, tests-only changes

Return a JSON array. Each element must have exactly these keys:
- "title": short task title (under 80 chars)
- "description": one-sentence description of what needs to be done
- "priority": one of "p0", "p1", "p2"

Return ONLY the JSON array, no markdown fences, no explanation.\
"""

REVIEW_SYSTEM_PROMPT = """\
You are a code review agent. You review the result of a worker that executed a software engineering task.

Given the original task and the worker's result, evaluate:
1. Was the task completed as described?
2. Are there obvious issues, missing pieces, or quality concerns?
3. What improvements could be made?

Return a JSON object with exactly these keys:
- "verdict": one of "accept" (task done well), "reject" (fundamentally wrong or incomplete), \
"partial" (partially done, needs more work)
- "feedback": a brief paragraph explaining your assessment
- "suggestions": an array of specific improvement suggestions (can be empty)

Return ONLY the JSON object, no markdown fences, no explanation.\
"""


def _parse_llm_json(text: str) -> list | dict:
    """Parse JSON from LLM output, stripping optional markdown code fences."""
    cleaned = text.strip()
    # Strip ```json ... ``` or ``` ... ```
    match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1).strip()
    return json.loads(cleaned)


def extract_memory_updates(text: str) -> tuple[str, list[dict]]:
    """Extract [MEMORY_UPDATE]...[/MEMORY_UPDATE] blocks from text.

    Returns:
        A tuple of (cleaned_text, list_of_memory_update_dicts).
    """
    pattern = r"\[MEMORY_UPDATE\](.*?)\[/MEMORY_UPDATE\]"
    updates: list[dict] = []
    for match in re.finditer(pattern, text, re.DOTALL):
        raw = match.group(1).strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                updates.append(parsed)
        except json.JSONDecodeError:
            logger.warning("master_agent.invalid_memory_update", raw=raw)

    cleaned = re.sub(pattern, "", text, flags=re.DOTALL).strip()
    return cleaned, updates


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
        self.memory_updates: list[dict] = []

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

        collected_response = []

        try:
            async for chunk in self._active_provider.stream(messages, **kwargs):
                collected_response.append(chunk)
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
                    collected_response.append(chunk)
                    yield chunk
            except Exception as fallback_err:
                logger.error(
                    "master_agent.all_providers_failed",
                    primary_error=str(primary_err),
                    fallback_error=str(fallback_err),
                )
                raise

        # Post-stream: extract memory updates from collected response
        full_response = "".join(collected_response)
        if "[MEMORY_UPDATE]" in full_response:
            _, updates = extract_memory_updates(full_response)
            if updates:
                self.memory_updates.extend(updates)
                logger.info("master_agent.memory_updates_extracted", count=len(updates))

    async def generate(self, history: list[ChatMessage], user_message: str, **kwargs) -> str:
        """Non-streaming version of chat. Returns complete response text."""
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            *history,
            ChatMessage(role="user", content=user_message),
        ]

        try:
            result = await self._active_provider.generate(messages, **kwargs)
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
            result = await self.fallback.generate(messages, **kwargs)

        # Extract memory updates
        if "[MEMORY_UPDATE]" in result:
            cleaned, updates = extract_memory_updates(result)
            if updates:
                self.memory_updates.extend(updates)
                logger.info("master_agent.memory_updates_extracted", count=len(updates))
            return cleaned

        return result

    def reset_to_primary(self) -> None:
        """Reset active provider back to primary (e.g., after transient failure resolves)."""
        if self._active_provider is not self.primary:
            logger.info("master_agent.reset_to_primary", from_provider=self._active_provider.provider_name)
            self._active_provider = self.primary

    async def classify_task(self, message: str) -> list[dict]:
        """Extract and classify tasks from a user message using LLM.

        Args:
            message: The user's raw message describing work to be done.

        Returns:
            A list of dicts, each with "title", "description", and "priority" keys.
        """
        messages = [
            ChatMessage(role="system", content=CLASSIFY_SYSTEM_PROMPT),
            ChatMessage(role="user", content=message),
        ]

        try:
            response = await self._active_provider.generate(messages, temperature=0.2)
        except Exception as primary_err:
            if self.fallback is None or self._active_provider is self.fallback:
                raise
            logger.warning("master_agent.classify_task.failover", error=str(primary_err))
            self._active_provider = self.fallback
            response = await self.fallback.generate(messages, temperature=0.2)

        try:
            tasks = _parse_llm_json(response)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("master_agent.classify_task.parse_error", response=response, error=str(e))
            # Fallback: treat entire message as a single P1 task
            tasks = [{"title": message[:80], "description": message, "priority": "p1"}]

        if not isinstance(tasks, list):
            tasks = [tasks]

        # Validate and normalize
        valid_priorities = {"p0", "p1", "p2"}
        for task in tasks:
            if task.get("priority", "").lower() not in valid_priorities:
                task["priority"] = "p1"
            else:
                task["priority"] = task["priority"].lower()

        return tasks

    def summarize_conversation(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        """Compress conversation history when it exceeds 10 messages.

        Keeps the most recent 6 messages intact and summarizes older ones
        into a single system message.

        Args:
            messages: Full conversation message list (excluding system prompt).

        Returns:
            Compressed message list. Returns original if <= 10 messages.
        """
        if len(messages) <= 10:
            return messages

        keep_recent = 6
        old_messages = messages[:-keep_recent]
        recent_messages = messages[-keep_recent:]

        # Build summary of old messages
        summary_parts = []
        for msg in old_messages:
            role_label = {"user": "User", "assistant": "Assistant", "system": "System"}.get(msg.role, msg.role)
            # Truncate long messages in summary
            content_preview = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
            summary_parts.append(f"- [{role_label}]: {content_preview}")

        summary_text = (
            "Summary of earlier conversation:\n" + "\n".join(summary_parts)
        )

        summary_message = ChatMessage(role="system", content=summary_text)
        return [summary_message, *recent_messages]

    async def review_worker_result(self, task: dict, result: dict) -> dict:
        """Review a worker's execution result using LLM.

        Args:
            task: The original task dict with at least "title" and "description".
            result: The worker result dict with execution details.

        Returns:
            A dict with "verdict" ("accept"|"reject"|"partial"),
            "feedback" (str), and "suggestions" (list[str]).
        """
        review_input = (
            f"## Original Task\n"
            f"Title: {task.get('title', 'N/A')}\n"
            f"Description: {task.get('description', 'N/A')}\n\n"
            f"## Worker Result\n"
            f"{json.dumps(result, indent=2, default=str)}"
        )

        messages = [
            ChatMessage(role="system", content=REVIEW_SYSTEM_PROMPT),
            ChatMessage(role="user", content=review_input),
        ]

        try:
            response = await self._active_provider.generate(messages, temperature=0.3)
        except Exception as primary_err:
            if self.fallback is None or self._active_provider is self.fallback:
                raise
            logger.warning("master_agent.review_worker.failover", error=str(primary_err))
            self._active_provider = self.fallback
            response = await self.fallback.generate(messages, temperature=0.3)

        try:
            review = _parse_llm_json(response)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("master_agent.review_worker.parse_error", response=response, error=str(e))
            review = {
                "verdict": "partial",
                "feedback": f"Failed to parse LLM review response: {e}",
                "suggestions": ["Manually review the worker output"],
            }

        if not isinstance(review, dict):
            review = {
                "verdict": "partial",
                "feedback": "LLM returned non-object response",
                "suggestions": ["Manually review the worker output"],
            }

        # Validate verdict
        valid_verdicts = {"accept", "reject", "partial"}
        if review.get("verdict") not in valid_verdicts:
            review["verdict"] = "partial"

        # Ensure required keys
        review.setdefault("feedback", "")
        review.setdefault("suggestions", [])

        return review
