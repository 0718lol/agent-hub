from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.config_persistence import get_hil_settings, save_hil_settings, save_llm_config
from app.core.llm_client import llm_client
from app.core.tenancy import current_tenant_id
from app.core.tenant_config import delete_tenant_config

router = APIRouter(tags=["settings"])
from app.core.logging_config import get_logger

logger = get_logger("settings")


class LLMSettings(BaseModel):
    provider: str = "openai"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = None
    max_tokens: int = None
    thinking_enabled: bool | None = None


class HILSettings(BaseModel):
    human_input_mode: Literal["NEVER", "ALWAYS", "AUTO"] = "NEVER"
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
        "thinking_enabled": llm_client.thinking_enabled,
        "configured": llm_client.is_configured(),
    }


@router.post("/settings/llm")
async def update_llm_settings(s: LLMSettings):
    thinking_enabled = s.thinking_enabled
    if thinking_enabled is None and "deepseek-v4-flash" in s.model.lower():
        thinking_enabled = False
    llm_client.configure(
        provider=s.provider,
        api_key=s.api_key if s.api_key else llm_client.api_key,
        base_url=s.base_url,
        model=s.model,
        temperature=s.temperature,
        max_tokens=s.max_tokens,
        thinking_enabled=thinking_enabled,
    )
    save_llm_config(llm_client, settings)
    return {"status": "ok", "configured": llm_client.is_configured()}


@router.delete("/settings/llm")
async def disconnect_llm_settings():
    tenant_id = current_tenant_id()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context is required")
    delete_tenant_config(tenant_id, "llm")
    llm_client.evict(tenant_id)
    inherited = bool(settings.llm_api_key and settings.llm_base_url)
    return {
        "status": "ok",
        "configured": llm_client.is_configured(),
        "provider": llm_client.provider,
        "model": llm_client.model,
        "inherited": inherited,
    }


@router.post("/settings/llm/test")
async def test_llm_connection():
    """测试当前 LLM 配置的连通性，发送一条最短消息验证 API 可用。"""
    if not llm_client.is_configured():
        return {"success": False, "error": "LLM 未配置（缺少 API Key 或 Base URL）"}

    try:
        response_text = ""
        async for chunk in llm_client.chat_stream(
            [{"role": "user", "content": "hi"}],
            system="Reply with only 'ok'.",
        ):
            response_text += chunk
            if len(response_text) > 20:
                break
        return {"success": True, "response": response_text.strip()[:50]}
    except Exception as e:
        return {"success": False, "error": str(e)[:500]}


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
    except Exception as e:
        logger.debug(f"Failed to fetch Ollama models: {e}")
    return []
