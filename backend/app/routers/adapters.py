"""Adapter Router — 适配器管理 API 端点。

提供：
- GET  /api/adapters — 查询所有适配器状态
- GET  /api/adapters/{agent_id} — 查询指定适配器状态
- POST /api/adapters — 创建/更新适配器配置
- DELETE /api/adapters/{agent_id} — 删除适配器
- POST /api/adapters/{agent_id}/test — 测试适配器连接
- POST /api/proxy/start — 启动本地 Agent 代理
- POST /api/proxy/stop — 停止本地 Agent 代理
- GET  /api/proxy/status — 查询代理状态
"""

import json
import logging
import asyncio
import os
import sys
import shlex
import subprocess
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
        tool_mode=config_dict.get("tool_mode", "agent"),
        extra=config_dict.get("extra", {}),
        display_name=config_dict.get("display_name", ""),
        display_avatar=config_dict.get("display_avatar", ""),
        display_desc=config_dict.get("display_desc", ""),
    )

    adapter = adapter_cls(config)
    adapter_registry.register(agent_id, adapter)

    # 同步更新 AGENTS 字典中的 AdapterAgent 包装器
    try:
        from app.services.agent_orchestrator import get_agents
        from app.adapters.adapter_agent import AdapterAgent
        agents = get_agents()
        if agent_id in agents:
            old = agents[agent_id]
            agents[agent_id] = AdapterAgent(
                agent_id=agent_id,
                name=getattr(old, 'name', adapter.name),
                adapter=adapter,
                avatar=getattr(old, 'avatar', '🤖'),
                role=getattr(old, 'role', adapter.description),
                system_prompt=getattr(old, 'system_prompt', ''),
            )
            logger.info(f"Updated AGENTS entry for {agent_id}")
    except Exception as e:
        logger.debug(f"Could not update AGENTS for {agent_id}: {e}")

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
    tool_mode: str = "agent"  # "agent" | "text" | "auto"
    extra: dict = {}
    display_name: str = ""    # 自定义显示名称
    display_avatar: str = ""  # 自定义头像
    display_desc: str = ""    # 自定义简介


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
        "tool_mode": req.tool_mode,
        "extra": req.extra,
        "display_name": req.display_name,
        "display_avatar": req.display_avatar,
        "display_desc": req.display_desc,
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
        # 检查响应是否包含错误标记
        if response.startswith("[") and "错误" in response:
            return {"status": "error", "error": response.strip("[]")}
        if response.startswith("[") and "error" in response.lower():
            return {"status": "error", "error": response.strip("[]")}
        return {"status": "ok", "response": response[:500]}
    except Exception as e:
        return {"status": "error", "error": str(e)[:500]}


# ---- 本地 Agent 代理管理 ----

_proxy_processes: dict[str, asyncio.subprocess.Process] = {}
PROXY_PORT = 4097
OPENCODE_PORT = 4098


@router.post("/proxy/start")
async def start_proxy():
    """启动本地 Agent 代理（OpenCode serve + Node.js proxy）。"""
    if "proxy" in _proxy_processes:
        return {"status": "already_running", "port": PROXY_PORT}

    # 项目根目录
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    proxy_script = os.path.join(project_root, "app", "proxy", "opencode_proxy.mjs")

    if not os.path.exists(proxy_script):
        return {"error": f"代理脚本不存在: {proxy_script}"}

    try:
        env = {**os.environ, "NODE_TLS_REJECT_UNAUTHORIZED": "0"}
        si = subprocess.STARTUPINFO() if sys.platform == "win32" else None
        if si:
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        # 清理可能残留的旧进程（端口为固定常量，非用户输入）
        for port in [OPENCODE_PORT, PROXY_PORT]:
            try:
                # nosec B602: 固定端口号，无注入风险；Windows 需 shell 执行管道命令
                out = subprocess.check_output(
                    f'netstat -ano | findstr ":{port}" | findstr LISTEN',
                    shell=True, text=True, stderr=subprocess.DEVNULL,
                ).strip()  # nosec B602
                if out:
                    pid = out.split()[-1]
                    if pid.isdigit():
                        subprocess.run(["taskkill", "/F", "/PID", pid],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    await asyncio.sleep(1)
            except Exception:
                pass

        # 1. 启动 opencode serve（参数为固定常量，使用列表避免 shell 注入）
        opencode_proc = subprocess.Popen(
            ["opencode", "serve", "--port", str(OPENCODE_PORT)],
            env=env, startupinfo=si,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        _proxy_processes["opencode"] = opencode_proc
        await asyncio.sleep(3)

        if opencode_proc.poll() is not None:
            return {"error": "opencode serve 启动失败，请检查 OpenCode 是否已安装"}

        # 2. 启动 Node.js 代理（脚本路径来自代码常量，非用户输入）
        proxy_proc = subprocess.Popen(
            ["node", proxy_script, "--port", str(PROXY_PORT),
             "--opencode-url", f"http://127.0.0.1:{OPENCODE_PORT}"],
            env=env, cwd=project_root, startupinfo=si,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        _proxy_processes["proxy"] = proxy_proc
        await asyncio.sleep(2)

        if proxy_proc.poll() is not None:
            stderr = proxy_proc.stderr.read().decode(errors="ignore")
            return {"error": f"代理启动失败: {stderr[:300]}"}

        return {"status": "started", "port": PROXY_PORT}

    except FileNotFoundError as e:
        return {"error": f"找不到可执行文件: {e}"}
    except Exception as e:
        return {"error": f"启动失败: {type(e).__name__}: {str(e)[:200]}"}


@router.post("/proxy/stop")
async def stop_proxy():
    """停止本地 Agent 代理。"""
    stopped = []
    for name, proc in _proxy_processes.items():
        try:
            proc.terminate()
            if sys.platform == "win32":
                # Windows: taskkill 杀掉整个进程树（pid 为系统分配的整数，无注入风险）
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            stopped.append(name)
        except Exception:
            pass
    _proxy_processes.clear()
    return {"status": "stopped", "stopped": stopped}


@router.get("/proxy/status")
async def proxy_status():
    """查询代理运行状态。"""
    running = {}
    for name, proc in list(_proxy_processes.items()):
        if proc.poll() is not None:
            _proxy_processes.pop(name, None)
        else:
            running[name] = True
    return {
        "running": len(running) > 0,
        "processes": list(running.keys()),
        "proxy_port": PROXY_PORT,
        "opencode_port": OPENCODE_PORT,
    }
