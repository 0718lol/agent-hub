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
                         language: str | None = None) -> str:
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


class TenantAwareSTTClient:
    """Resolve speech settings per active tenant while retaining a local default."""

    def __init__(self):
        self._default = STTClient()
        self._clients: dict[str, STTClient] = {}

    def _client(self) -> STTClient:
        from app.core.config import deobfuscate_key
        from app.core.tenancy import current_tenant_id
        from app.core.tenant_config import get_tenant_json

        tenant_id = current_tenant_id()
        if not tenant_id:
            return self._default
        existing = self._clients.get(tenant_id)
        if existing is not None:
            return existing

        config = get_tenant_json(tenant_id, "stt", {}, encrypted=True) or {}
        client = STTClient()
        client.configure(
            api_key=deobfuscate_key(config.get("api_key", "")) or self._default.api_key,
            base_url=config.get("base_url", "") or self._default.base_url,
            model=config.get("model", "") or self._default.model,
            language=config.get("language", "") or self._default.language,
        )
        self._clients[tenant_id] = client
        return client

    def configure(self, api_key: str, base_url: str, model: str = "whisper-1", language: str = "zh"):
        self._client().configure(api_key, base_url, model, language)

    def __getattr__(self, name):
        return getattr(self._client(), name)

    def evict(self, tenant_id: str) -> None:
        self._clients.pop(tenant_id, None)


stt_client = TenantAwareSTTClient()
