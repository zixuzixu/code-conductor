"""Tests for the voice transcription API endpoint."""

from io import BytesIO
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from conductor.api.deps import get_config


FAKE_AUDIO = b"\x00\x01\x02" * 100


def _client():
    get_config.cache_clear()
    from server import app

    return TestClient(app, raise_server_exceptions=False)


class TestVoiceEndpoint:
    def test_rejects_non_audio_content_type(self):
        client = _client()
        resp = client.post(
            "/api/voice",
            files={"audio": ("test.txt", BytesIO(b"hello"), "text/plain")},
        )
        assert resp.status_code == 400
        assert "audio" in resp.json()["detail"].lower()

    def test_rejects_oversized_audio(self):
        client = _client()
        big = b"\x00" * (26 * 1024 * 1024)
        resp = client.post(
            "/api/voice",
            files={"audio": ("big.webm", BytesIO(big), "audio/webm")},
        )
        assert resp.status_code == 413

    @patch.dict("os.environ", {"GEMINI_API_KEY": ""})
    def test_returns_503_when_no_api_key(self):
        client = _client()
        config = get_config()
        config.primary_llm.api_key = ""

        resp = client.post(
            "/api/voice",
            files={"audio": ("test.webm", BytesIO(FAKE_AUDIO), "audio/webm")},
        )
        assert resp.status_code == 503

    @patch("conductor.api.voice._transcribe_with_gemini", new_callable=AsyncMock, return_value="Hello world")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    def test_successful_transcription(self, mock_transcribe):
        client = _client()
        resp = client.post(
            "/api/voice",
            files={"audio": ("test.webm", BytesIO(FAKE_AUDIO), "audio/webm")},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "Hello world"
        assert "voice-transcribed" in data["disclaimer"]
        mock_transcribe.assert_called_once()

    @patch("conductor.api.voice._transcribe_with_gemini", new_callable=AsyncMock, return_value="")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    def test_empty_transcription_returns_422(self, mock_transcribe):
        client = _client()
        resp = client.post(
            "/api/voice",
            files={"audio": ("test.webm", BytesIO(FAKE_AUDIO), "audio/webm")},
        )

        assert resp.status_code == 422

    @patch("conductor.api.voice._transcribe_with_gemini", new_callable=AsyncMock, side_effect=ImportError("no google"))
    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    def test_import_error_returns_503(self, mock_transcribe):
        client = _client()
        resp = client.post(
            "/api/voice",
            files={"audio": ("test.webm", BytesIO(FAKE_AUDIO), "audio/webm")},
        )
        assert resp.status_code == 503

    def test_disclaimer_text_matches_spec(self):
        from conductor.api.voice import DISCLAIMER

        assert "voice-transcribed" in DISCLAIMER
        assert "clarifying questions" in DISCLAIMER
