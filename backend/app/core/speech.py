"""
Speech-to-Text client.

Supports:
  1. OpenAI Whisper API (and compatible endpoints like Groq, Azure, etc.)
  2. Browser-native Web Speech API fallback (handled on frontend)

Usage:
  from app.core.speech import stt_client
  text = await stt_client.transcribe(audio_bytes, filename="audio.webm")
"""

import httpx
from typing import Optional


class STTClient:
    """Speech-to-Text client using OpenAI Whisper-compatible API."""

    def __init__(self):
        self.api_key: str = ""
        self.base_url: str = ""
        self.model: str = "whisper-1"
        self.language: str = "zh"

    def configure(self, api_key: str, base_url: str, model: str = "whisper-1",
                  language: str = "zh"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.language = language

    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm",
                         language: Optional[str] = None) -> str:
        """
        Transcribe audio bytes to text.

        Args:
            audio_bytes: Raw audio file bytes
            filename: Original filename (used for content-type detection)
            language: Override language code (e.g. 'zh', 'en')

        Returns:
            Transcribed text string

        Raises:
            Exception on API errors
        """
        if not self.is_configured():
            raise RuntimeError("STT not configured. Set API key and base URL first.")

        url = f"{self.base_url}/audio/transcriptions"
        if not url.startswith("http"):
            url = f"https://{url}"

        # Determine content type from filename
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "webm"
        content_types = {
            "webm": "audio/webm",
            "wav": "audio/wav",
            "mp3": "audio/mpeg",
            "m4a": "audio/mp4",
            "ogg": "audio/ogg",
            "flac": "audio/flac",
        }
        content_type = content_types.get(ext, "audio/webm")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        files = {
            "file": (filename, audio_bytes, content_type),
        }
        data = {
            "model": self.model,
            "language": language or self.language,
            "response_format": "json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, files=files, data=data)

            if resp.status_code != 200:
                error_text = resp.text[:300]
                raise RuntimeError(f"STT API error {resp.status_code}: {error_text}")

            result = resp.json()
            return result.get("text", "")


stt_client = STTClient()
