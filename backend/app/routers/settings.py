import asyncio
from typing import Literal

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.config_persistence import get_hil_settings
from app.core.tenancy import request_user_id
from app.core.tenant_settings import (
    get_tenant_config,
    get_tenant_llm_client,
    save_tenant_config,
    save_tenant_llm_client,
)

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


class HILSettings(BaseModel):
    human_input_mode: Literal["NEVER", "ALWAYS", "AUTO", "COOLDOWN"] = "NEVER"
    cooldown_steps: int = Field(default=2, ge=1, le=100)


@router.get("/settings/llm")
async def get_llm_settings(request: Request):
    client = await asyncio.to_thread(get_tenant_llm_client, request_user_id(request))
    return {
        "provider": client.provider,
        "api_key_set": bool(client.api_key),
        "base_url": client.base_url,
        "model": client.model,
        "temperature": client.temperature,
        "max_tokens": client.max_tokens,
        "configured": client.is_configured(),
    }


@router.post("/settings/llm")
async def update_llm_settings(s: LLMSettings, request: Request):
    user_id = request_user_id(request)
    client = await asyncio.to_thread(get_tenant_llm_client, user_id)
    client.configure(
        provider=s.provider,
        api_key=s.api_key if s.api_key else client.api_key,
        base_url=s.base_url,
        model=s.model,
        temperature=s.temperature,
        max_tokens=s.max_tokens,
    )
    await asyncio.to_thread(save_tenant_llm_client, user_id, client)
    return {"status": "ok", "configured": client.is_configured()}


@router.post("/settings/llm/test")
async def test_llm_connection(request: Request):
    """测试当前 LLM 配置的连通性，发送一条最短消息验证 API 可用。"""
    client = await asyncio.to_thread(get_tenant_llm_client, request_user_id(request))
    if not client.is_configured():
        return {"success": False, "error": "LLM 未配置（缺少 API Key 或 Base URL）"}

    try:
        response_text = ""
        async for chunk in client.chat_stream(
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
async def get_hil_settings_api(request: Request):
    return await asyncio.to_thread(
        get_tenant_config,
        request_user_id(request),
        "hil",
        get_hil_settings(),
    )


@router.post("/settings/hil")
async def update_hil_settings_api(s: HILSettings, request: Request):
    cfg = {
        "human_input_mode": s.human_input_mode,
        "cooldown_steps": s.cooldown_steps
    }
    await asyncio.to_thread(save_tenant_config, request_user_id(request), "hil", cfg)
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
