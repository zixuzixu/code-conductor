"""Chat endpoint — SSE streaming with Master Agent."""

from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from conductor.agents.llm_provider import ChatMessage
from conductor.api.deps import get_config, get_session_manager

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = structlog.get_logger()

MAX_CHAT_MESSAGE_LENGTH = 100_000  # 100KB limit per message


class ChatRequest(BaseModel):
    session_id: UUID
    message: str

    @field_validator("message")
    @classmethod
    def validate_message_length(cls, v: str) -> str:
        if len(v) > MAX_CHAT_MESSAGE_LENGTH:
            raise ValueError(f"Message exceeds maximum length of {MAX_CHAT_MESSAGE_LENGTH} characters")
        if not v.strip():
            raise ValueError("Message must not be empty")
        return v


def _build_master_agent():
    """Build MasterAgent from current config. Lazy import to avoid import-time side effects."""
    from conductor.agents.gemini_provider import GeminiProvider
    from conductor.agents.kimi_provider import KimiProvider
    from conductor.agents.master_agent import MasterAgent

    config = get_config()
    primary = GeminiProvider(config.primary_llm)
    fallback = KimiProvider(config.fallback_llm)
    return MasterAgent(primary=primary, fallback=fallback)


@router.post("")
async def chat(req: ChatRequest):
    """Stream a Master Agent response via SSE (text/event-stream).

    The session's conversation_history is used as context.
    The user message and assistant response are appended to history.
    """
    mgr = get_session_manager()
    session = mgr.get_session(req.session_id)
    if session is None:
        raise HTTPException(404, "Session not found")

    # Convert stored history dicts to ChatMessage objects
    history = [ChatMessage(**m) for m in session.conversation_history]

    agent = _build_master_agent()

    async def event_stream():
        chunks: list[str] = []
        try:
            async for chunk in agent.chat(history, req.message):
                chunks.append(chunk)
                # SSE format: data: <text>\n\n
                yield f"data: {chunk}\n\n"
        except Exception as e:
            logger.error("chat.stream_error", error=str(e))
            yield f"event: error\ndata: {e!s}\n\n"
            return

        # Persist conversation to session
        full_response = "".join(chunks)
        session.conversation_history.append({"role": "user", "content": req.message})
        session.conversation_history.append({"role": "assistant", "content": full_response})
        mgr.update_session(session)

        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
