"""Voice transcription endpoint using Gemini API."""

import os

import structlog
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from conductor.api.deps import get_config

router = APIRouter(prefix="/api/voice", tags=["voice"])
logger = structlog.get_logger()

DISCLAIMER = (
    "This is a voice-transcribed message and may not be exactly accurate. "
    "Please ask clarifying questions if anything is unclear."
)

MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25MB limit


class TranscriptionResponse(BaseModel):
    text: str
    disclaimer: str


def _get_gemini_api_key() -> str:
    """Resolve Gemini API key from env var or config."""
    config = get_config()
    key = os.environ.get("GEMINI_API_KEY") or config.primary_llm.api_key
    if not key:
        raise HTTPException(503, "Gemini API key not configured")
    return key


async def _transcribe_with_gemini(api_key: str, audio_data: bytes, mime_type: str) -> str:
    """Call Gemini API to transcribe audio. Separated for testability."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = await client.aio.models.generate_content(
        model="gemini-2.0-flash",
        contents=[
            types.Content(
                parts=[
                    types.Part.from_bytes(data=audio_data, mime_type=mime_type),
                    types.Part.from_text(
                        "Transcribe this audio accurately. Output only the transcription text, "
                        "nothing else. Support Chinese, English, and mixed languages."
                    ),
                ]
            )
        ],
    )
    return (response.text or "").strip()


@router.post("", response_model=TranscriptionResponse)
async def transcribe(audio: UploadFile):
    """Transcribe uploaded audio using Gemini API.

    Accepts audio files (webm, wav, mp3, ogg, m4a).
    Returns transcribed text with a disclaimer.
    """
    if not audio.content_type or not audio.content_type.startswith("audio/"):
        raise HTTPException(400, "File must be an audio format")

    content = await audio.read()
    if len(content) > MAX_AUDIO_SIZE:
        raise HTTPException(413, f"Audio file exceeds {MAX_AUDIO_SIZE // (1024 * 1024)}MB limit")

    api_key = _get_gemini_api_key()
    mime = audio.content_type or "audio/webm"

    try:
        text = await _transcribe_with_gemini(api_key, content, mime)
    except ImportError as exc:
        raise HTTPException(503, "google-genai package not installed") from exc
    except Exception as e:
        logger.error("voice.transcription_error", error=str(e))
        raise HTTPException(500, f"Transcription failed: {e}") from e

    if not text:
        raise HTTPException(422, "Could not transcribe audio — no speech detected")

    logger.info("voice.transcribed", length=len(text), mime=mime)
    return TranscriptionResponse(text=text, disclaimer=DISCLAIMER)
