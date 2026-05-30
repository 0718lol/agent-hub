import httpx
from fastapi import APIRouter
from pydantic import BaseModel
from app.core.config import settings
from app.core.llm_client import llm_client
from app.core.config_persistence import get_hil_settings, save_hil_settings, save_llm_config

router = APIRouter(tags=["settings"])


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
    save_llm_config(llm_client, settings)
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
    save_hil_settings(cfg)
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
