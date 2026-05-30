import os
import json
import httpx
from fastapi import APIRouter
from pydantic import BaseModel
from app.core.config import settings, obfuscate_key
from app.core.llm_client import llm_client

router = APIRouter(tags=["settings"])

LLM_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "llm_config.json")
HIL_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "hil_config.json")


def get_hil_settings() -> dict:
    try:
        if os.path.exists(HIL_CONFIG_PATH):
            with open(HIL_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"human_input_mode": "NEVER", "cooldown_steps": 2}


def _save_hil_settings(cfg: dict):
    os.makedirs(os.path.dirname(HIL_CONFIG_PATH), exist_ok=True)
    with open(HIL_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _save_llm_config():
    os.makedirs(os.path.dirname(LLM_CONFIG_PATH), exist_ok=True)
    api_key_to_save = llm_client.api_key
    # 如果 API Key 与系统默认 Pydantic Key 或者是系统环境变量 Key 相同，安全地对落盘值进行置空过滤
    if api_key_to_save == settings.llm_api_key or api_key_to_save == os.environ.get("ANTHROPIC_API_KEY", ""):
        api_key_to_save = ""
    else:
        api_key_to_save = obfuscate_key(api_key_to_save)
        
    with open(LLM_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "provider": llm_client.provider,
            "api_key": api_key_to_save,
            "base_url": llm_client.base_url,
            "model": llm_client.model,
            "temperature": llm_client.temperature,
            "max_tokens": llm_client.max_tokens,
        }, f, ensure_ascii=False, indent=2)


class LLMSettings(BaseModel):
    provider: str = "openai"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = None
    max_tokens: int = None


class HILSettings(BaseModel):
    human_input_mode: str = "NEVER"
    cooldown_steps: int = 2


@router.get("/settings/llm")
async def get_llm_settings():
    return {
        "provider": llm_client.provider,
        "api_key_set": bool(llm_client.api_key),
        "base_url": llm_client.base_url,
        "model": llm_client.model,
        "temperature": llm_client.temperature,
        "max_tokens": llm_client.max_tokens,
        "configured": llm_client.is_configured(),
    }


@router.post("/settings/llm")
async def update_llm_settings(s: LLMSettings):
    llm_client.configure(
        provider=s.provider,
        api_key=s.api_key if s.api_key else llm_client.api_key,
        base_url=s.base_url,
        model=s.model,
        temperature=s.temperature,
        max_tokens=s.max_tokens,
    )
    _save_llm_config()
    return {"status": "ok", "configured": llm_client.is_configured()}


@router.get("/settings/hil")
async def get_hil_settings_api():
    return get_hil_settings()


@router.post("/settings/hil")
async def update_hil_settings_api(s: HILSettings):
    cfg = {
        "human_input_mode": s.human_input_mode,
        "cooldown_steps": s.cooldown_steps
    }
    _save_hil_settings(cfg)
    return {"status": "ok", "settings": cfg}


@router.get("/ollama/models")
async def list_ollama_models():
    """Fetch installed models from local Ollama instance."""
    url = "http://127.0.0.1:11434/api/tags"
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    return []
