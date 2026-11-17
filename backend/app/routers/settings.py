from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.config_persistence import get_hil_settings, save_hil_settings, save_llm_config
from app.core.llm_client import llm_client
from app.core.tenancy import current_tenant_id, is_request_admin
from app.core.tenant_config import delete_tenant_config
from app.tools.http_request import validate_outbound_url

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
    thinking_mode: Literal["auto", "enabled", "disabled"] | None = None


class HILSettings(BaseModel):
    human_input_mode: Literal["NEVER", "ALWAYS", "AUTO", "COOLDOWN"] = "NEVER"
    cooldown_steps: int = Field(default=2, gt=0)


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
        "thinking_mode": llm_client.thinking_mode,
        "configured": llm_client.is_configured(),
    }


@router.post("/settings/llm")
async def update_llm_settings(s: LLMSettings, request: Request):
    admin_caller = is_request_admin(request)
    if s.provider in ("opencode", "claude_code", "ollama") and not admin_caller:
        raise HTTPException(status_code=403, detail="仅管理员可配置宿主级本地模型或 CLI 提供商")
    if s.base_url.strip():
        ssrf_err = validate_outbound_url(
            s.base_url.strip(),
            allow_loopback=admin_caller,
            resolve_dns=False,
        )
        if ssrf_err:
            raise HTTPException(status_code=422, detail=ssrf_err)
    thinking_enabled = s.thinking_enabled
    thinking_mode = s.thinking_mode
    if thinking_mode is None and thinking_enabled is not None:
        thinking_mode = "enabled" if thinking_enabled else "disabled"
    if thinking_enabled is None and thinking_mode in ("enabled", "disabled"):
        thinking_enabled = thinking_mode == "enabled"
    if thinking_enabled is None and thinking_mode is None and "deepseek-v4-flash" in s.model.lower():
        thinking_enabled = False
        thinking_mode = "disabled"
    llm_client.configure(
        provider=s.provider,
        api_key=s.api_key or llm_client.retained_api_key(s.provider, s.base_url),
        base_url=s.base_url,
        model=s.model,
        temperature=s.temperature,
        max_tokens=s.max_tokens,
        thinking_enabled=thinking_enabled,
        thinking_mode=thinking_mode,
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
            if len(response_text) > 120:
                break
        cleaned = response_text.strip()
        lowered = cleaned.lower()
        if not cleaned or any(
            marker in lowered
            for marker in (
                "[llm 终端错误",
                "[llm 调用出错",
                "[llm 故障已触发熔断保护",
                "llm api error",
                "❌ [所有 llm 服务",
                "[ollama 本地降级",
                "[云端备份提供商",
            )
        ):
            return {"success": False, "error": cleaned[:500] or "模型未返回有效响应"}
        return {"success": True, "response": cleaned[:50]}
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
async def list_ollama_models(request: Request):
    """Fetch installed models from local Ollama instance (admin only in multi-tenant mode)."""
    if not is_request_admin(request):
        return {
            "status": "error",
            "models": [],
            "message": "仅管理员可访问服务器本机 Ollama 模型列表",
        }
    url = "http://127.0.0.1:11434/api/tags"
    try:
        async with httpx.AsyncClient(timeout=1.5, trust_env=False) as client:
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                models = [m["name"] for m in data.get("models", []) if isinstance(m, dict) and m.get("name")]
                return {"status": "ok", "models": models}
    except Exception as e:
        logger.debug(f"Failed to fetch Ollama models: {e}")
    return {"status": "error", "models": [], "message": "未检测到正在运行的本地 Ollama 服务 (127.0.0.1:11434)"}
