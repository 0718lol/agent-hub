"""Speech-to-text settings and transcription endpoints."""
import os
import json
import logging
from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel
from app.core.speech import stt_client
from app.core.llm_client import llm_client
from app.core.config import obfuscate_key as encrypt_key, deobfuscate_key as decrypt_key

logger = logging.getLogger("routers.speech")
router = APIRouter(tags=["speech"])

STT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "stt_config.json")


def _load_stt_config():
    try:
        if os.path.exists(STT_CONFIG_PATH):
            with open(STT_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            api_key = cfg.get("api_key", "")
            api_key = decrypt_key(api_key)
            stt_client.configure(
                api_key=api_key,
                base_url=cfg.get("base_url", ""),
                model=cfg.get("model", "whisper-1"),
                language=cfg.get("language", "zh"),
            )
    except Exception as e:
        logger.warning(f"Failed to load STT config: {e}")


def _save_stt_config():
    try:
        os.makedirs(os.path.dirname(STT_CONFIG_PATH), exist_ok=True)
        obfuscated_api_key = encrypt_key(stt_client.api_key)
        with open(STT_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "api_key": obfuscated_api_key,
                "base_url": stt_client.base_url,
                "model": stt_client.model,
                "language": stt_client.language,
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save STT config: {e}")


# Load STT config on module import
_load_stt_config()


class STTSettings(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = "whisper-1"
    language: str = "zh"


@router.get("/settings/stt")
async def get_stt_settings():
    return {
        "configured": stt_client.is_configured(),
        "base_url": stt_client.base_url,
        "model": stt_client.model,
        "language": stt_client.language,
    }


@router.post("/settings/stt")
async def update_stt_settings(s: STTSettings):
    stt_client.configure(
        api_key=s.api_key or stt_client.api_key,
        base_url=s.base_url,
        model=s.model,
        language=s.language,
    )
    _save_stt_config()
    return {"configured": stt_client.is_configured()}


@router.post("/speech/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Upload an audio file and get transcribed text back."""
    audio_bytes = await file.read()
    filename = file.filename or "audio.webm"

    if not stt_client.is_configured() and llm_client.is_configured():
        stt_client.configure(
            api_key=llm_client.api_key,
            base_url=llm_client.base_url,
            model="whisper-1",
            language="zh",
        )

    if not stt_client.is_configured():
        return {"error": "语音识别未配置。请在设置中配置 STT API 或 LLM API。", "text": ""}

    try:
        text = await stt_client.transcribe(audio_bytes, filename)
        return {"text": text, "status": "ok"}
    except Exception as e:
        return {"error": f"语音识别失败: {str(e)[:200]}", "text": ""}
