"""Adapter Router — 适配器管理 API 端点。

提供：
- GET  /api/adapters — 查询所有适配器状态
- GET  /api/adapters/{agent_id} — 查询指定适配器状态
- POST /api/adapters — 创建/更新适配器配置
- DELETE /api/adapters/{agent_id} — 删除适配器
- POST /api/adapters/{agent_id}/test — 测试适配器连接
"""

import json
import logging
from pydantic import BaseModel
from typing import Optional
from fastapi import APIRouter

from app.adapters.base import AdapterConfig
from app.adapters.registry import adapter_registry

logger = get_logger = logging.getLogger("adapter_router")

# 延迟导入适配器类，避免 httpx 等依赖缺失时导致整个 app 崩溃
ADAPTER_CLASSES = {}
try:
    from app.adapters.claude_adapter import ClaudeAdapter
    ADAPTER_CLASSES["claude"] = ClaudeAdapter
except ImportError as e:
    logger.warning(f"ClaudeAdapter unavailable: {e}")

try:
    from app.adapters.codex_adapter import CodexAdapter
    ADAPTER_CLASSES["codex"] = CodexAdapter
except ImportError as e:
    logger.warning(f"CodexAdapter unavailable: {e}")

try:
    from app.adapters.coze_adapter import CozeAdapter
    ADAPTER_CLASSES["coze"] = CozeAdapter
except ImportError as e:
    logger.warning(f"CozeAdapter unavailable: {e}")

try:
    from app.adapters.self_deployed_adapter import SelfDeployedAdapter, DifyAdapter
    ADAPTER_CLASSES["self_deployed"] = SelfDeployedAdapter
    ADAPTER_CLASSES["dify"] = DifyAdapter
except ImportError as e:
    logger.warning(f"SelfDeployedAdapter unavailable: {e}")

router = APIRouter(tags=["adapters"])


# ---- Adapter Factory ----


def create_adapter(agent_id: str, config_dict: dict, save: bool = True) -> bool:
    """根据配置创建适配器实例并注册。

    Args:
        agent_id: Agent ID
        config_dict: 配置字典
        save: 是否持久化配置（预注册占位适配器时设为 False）
    """
    adapter_type = config_dict.get("adapter_type", "")
    adapter_cls = ADAPTER_CLASSES.get(adapter_type)

    if not adapter_cls:
        logger.error(f"Unknown adapter type: {adapter_type}")
        return False

    config = AdapterConfig(
        adapter_type=adapter_type,
        api_key=config_dict.get("api_key", ""),
        api_url=config_dict.get("api_url", ""),
        model=config_dict.get("model", ""),
        timeout=config_dict.get("timeout", 60),
        max_retries=config_dict.get("max_retries", 2),
        extra=config_dict.get("extra", {}),
    )

    adapter = adapter_cls(config)
    adapter_registry.register(agent_id, adapter)
    if save:
        adapter_registry.save_config(agent_id, config_dict)
    return True


def load_saved_adapters():
    """从持久化配置加载所有已保存的适配器。"""
    configs = adapter_registry.get_saved_configs()
    for agent_id, config_dict in configs.items():
        try:
            create_adapter(agent_id, config_dict)
        except Exception as e:
            logger.warning(f"Failed to load adapter {agent_id}: {e}")


# ---- Request/Response Models ----

class AdapterCreateRequest(BaseModel):
    agent_id: str
    adapter_type: str         # "claude" | "codex" | "coze" | "self_deployed" | "dify"
    name: str = ""
    api_key: str = ""
    api_url: str = ""
    model: str = ""
    timeout: int = 60
    extra: dict = {}


class AdapterTestRequest(BaseModel):
    message: str = "你好，请简单介绍一下你自己。"


# ---- API Endpoints ----

@router.get("/adapters")
async def list_adapters():
    """查询所有适配器状态。"""
    statuses = adapter_registry.get_all_status()
    return {"adapters": statuses}


@router.get("/adapters/{agent_id}")
async def get_adapter(agent_id: str):
    """查询指定适配器状态。"""
    status = adapter_registry.get_status_by_id(agent_id)
    if not status:
        return {"error": f"Adapter not found: {agent_id}"}
    return status


@router.post("/adapters")
async def create_or_update_adapter(req: AdapterCreateRequest):
    """创建或更新适配器配置。"""
    config_dict = {
        "adapter_type": req.adapter_type,
        "api_key": req.api_key,
        "api_url": req.api_url,
        "model": req.model,
        "timeout": req.timeout,
        "extra": req.extra,
    }

    success = create_adapter(req.agent_id, config_dict)
    if not success:
        return {"error": f"Unknown adapter type: {req.adapter_type}"}

    return {"status": "ok", "agent_id": req.agent_id}


@router.delete("/adapters/{agent_id}")
async def delete_adapter(agent_id: str):
    """删除适配器。"""
    adapter_registry.unregister(agent_id)
    adapter_registry.remove_config(agent_id)
    return {"status": "deleted", "agent_id": agent_id}


@router.post("/adapters/{agent_id}/test")
async def test_adapter(agent_id: str, req: AdapterTestRequest):
    """测试适配器连接（发送一条测试消息）。"""
    adapter = adapter_registry.get(agent_id)
    if not adapter:
        return {"error": f"Adapter not found: {agent_id}"}

    valid, err = adapter.validate_config()
    if not valid:
        return {"error": err}

    try:
        response = ""
        async for chunk in adapter.stream_reply(req.message):
            response += chunk
            if len(response) > 500:
                break
        return {"status": "ok", "response": response[:500]}
    except Exception as e:
        return {"error": str(e)[:200]}
