import asyncio
import shutil
import socket
import os
import json
import httpx
from typing import List, Dict

# Path to register prompt layers
PROMPT_LAYER_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "core", "prompt_engine.py"))

async def is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        conn = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(conn, timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False

async def get_running_processes() -> List[str]:
    processes = []
    # Try Windows-specific PowerShell detection first
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-Command", "Get-Process | Select-Object -ExpandProperty ProcessName",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            lines = stdout.decode("utf-8", errors="replace").splitlines()
            return [line.strip().lower() for line in lines if line.strip()]
    except Exception:
        pass

    # Fallback to tasklist
    try:
        proc = await asyncio.create_subprocess_exec(
            "tasklist", "/fo", "csv", "/nh",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            lines = stdout.decode("utf-8", errors="replace").splitlines()
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split(",")
                if parts:
                    name = parts[0].replace('"', '').strip().lower()
                    if name.endswith(".exe"):
                        name = name[:-4]
                    processes.append(name)
            return processes
    except Exception:
        pass
    return []

async def detect_local_ai_tools() -> List[Dict]:
    detected = []
    running_procs = await get_running_processes()
    
    # 1. Ollama
    ollama_running = "ollama" in running_procs or await is_port_open("127.0.0.1", 11434)
    ollama_installed = shutil.which("ollama") is not None
    ollama_models = []
    if ollama_running:
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                r = await client.get("http://127.0.0.1:11434/api/tags")
                if r.status_code == 200:
                    data = r.json()
                    ollama_models = [m["name"] for m in data.get("models", [])]
        except Exception:
            pass

    detected.append({
        "id": "ollama",
        "name": "Ollama 本地大模型服务",
        "icon": "🦙",
        "status": "running" if ollama_running else ("installed" if ollama_installed else "absent"),
        "description": "本地大模型推理引擎，支持 DeepSeek、Llama 等开源模型。",
        "address": "http://127.0.0.1:11434",
        "models": ollama_models,
        "details": f"已下载模型: {', '.join(ollama_models)}" if ollama_models else "未检测到已下载模型",
        "suggested_llm_settings": {
            "provider": "ollama",
            "base_url": "http://127.0.0.1:11434/v1",
            "model": ollama_models[0] if ollama_models else "deepseek-r1:7b"
        },
        "suggested_prompt_addon": "本地已连接 Ollama 大模型引擎，支持使用本地离线模型进行推理与交互。",
        "suggested_tool": {
            "id": "ollama_chat",
            "name": "Ollama本地推理",
            "icon": "🦙",
            "description": "调用本地正在运行的 Ollama 模型进行文本推理与辅助分析。"
        }
    })

    # 2. Claude Code
    # Usually runs inside node CLI so process name might be node, we check PATH and global node modules or processes
    claude_code_installed = shutil.which("claude") is not None
    claude_code_running = any("claude" in p for p in running_procs)
    
    # We can also check if `@anthropic-ai/claude-code` package or `claude-code-sdk` is installed
    sdk_installed = False
    try:
        import claude_code_sdk
        sdk_installed = True
    except ImportError:
        pass

    detected.append({
        "id": "claude_code",
        "name": "Claude Code (Anthropic CLI)",
        "icon": "🤖",
        "status": "running" if claude_code_running else ("installed" if (claude_code_installed or sdk_installed) else "absent"),
        "description": "Anthropic 官方的高性能终端 AI 编程助手与代码审查工具。",
        "details": "支持极致的代码修改与多文件协同，内置高质量测试与质量控制流程。" if (claude_code_installed or sdk_installed) else "未在 PATH 中检测到 'claude' 命令行工具。",
        "suggested_llm_settings": {
            "provider": "claude_code",
            "base_url": "",
            "model": "claude-3-5-sonnet-20241022"
        },
        "suggested_prompt_addon": "本地已安装并接入 Claude Code 命令行编程工具，支持进行深度的代码重构与质量检测。",
        "suggested_tool": {
            "id": "claude_code_cli",
            "name": "Claude Code 协同",
            "icon": "🤖",
            "description": "唤醒本地 Claude Code 强大的多文件级修改与命令行编程协同能力。"
        }
    })

    # 3. LM Studio
    lm_studio_running = "lm studio" in running_procs or "lmstudio" in running_procs or await is_port_open("127.0.0.1", 1234)
    lm_models = []
    if lm_studio_running:
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                r = await client.get("http://127.0.0.1:1234/v1/models")
                if r.status_code == 200:
                    data = r.json()
                    lm_models = [m["id"] for m in data.get("data", [])]
        except Exception:
            pass

    detected.append({
        "id": "lm_studio",
        "name": "LM Studio 服务",
        "icon": "💻",
        "status": "running" if lm_studio_running else "absent",
        "description": "本地模型运行软件，提供与 OpenAI 兼容的本地 API 接口。",
        "address": "http://127.0.0.1:1234",
        "details": f"当前加载模型: {', '.join(lm_models)}" if lm_models else "服务开启中，未加载或未检测到模型",
        "suggested_llm_settings": {
            "provider": "openai",
            "base_url": "http://127.0.0.1:1234/v1",
            "model": lm_models[0] if lm_models else "local-model"
        },
        "suggested_prompt_addon": "本地已运行 LM Studio 兼容服务，支持作为高性能本地低延迟大模型使用。",
        "suggested_tool": {
            "id": "lm_studio_completion",
            "name": "LMStudio本地生成",
            "icon": "💻",
            "description": "通过本地 LM Studio 实例进行快速文本生成与模式过滤。"
        }
    })

    # 4. OpenCode
    opencode_installed = shutil.which("opencode") is not None
    opencode_running = "opencode" in running_procs

    detected.append({
        "id": "opencode",
        "name": "OpenCode CLI 工具",
        "icon": "🔌",
        "status": "running" if opencode_running else ("installed" if opencode_installed else "absent"),
        "description": "开源代码智能体生成与任务编排命令行工具。",
        "details": "支持本地/远端大模型驱动的代码逻辑自动化开发流程。" if opencode_installed else "未检测到本地安装，请使用 go 或者是安装脚本安装。",
        "suggested_llm_settings": {
            "provider": "opencode",
            "base_url": "",
            "model": "default"
        },
        "suggested_prompt_addon": "本地已就绪 OpenCode 终端智能体，支持无缝接收需求并离线生成工程化项目骨架。",
        "suggested_tool": {
            "id": "opencode_workflow",
            "name": "OpenCode工作流",
            "icon": "🔌",
            "description": "触发 OpenCode 的多阶段代理生成机制来完成复杂的系统级代码编写。"
        }
    })

    # 5. Cursor & VS Code
    cursor_running = "cursor" in running_procs
    vscode_running = "code" in running_procs
    ide_running = cursor_running or vscode_running

    detected.append({
        "id": "cursor_vscode",
        "name": "Cursor / VS Code 编辑器",
        "icon": "🎨",
        "status": "running" if ide_running else "absent",
        "description": "用户当前正在使用的代码编辑与辅助编程集成开发环境（IDE）。",
        "details": f"检测到正在运行: {'Cursor' if cursor_running else ''} {'VS Code' if vscode_running else ''}".strip(),
        "suggested_prompt_addon": f"用户当前正使用 {'Cursor' if cursor_running else 'VS Code'} 进行开发，建议生成的代码注重高兼容性，并配合 IDE 原生的快捷辅助能力。",
    })

    # 6. Aider
    aider_installed = shutil.which("aider") is not None
    aider_running = "aider" in running_procs

    detected.append({
        "id": "aider",
        "name": "Aider AI 结对编程助手",
        "icon": "🧙‍♂️",
        "status": "running" if aider_running else ("installed" if aider_installed else "absent"),
        "description": "命令行 AI 编程协同工具，完美适配 Git 版本控制与自动回滚。",
        "details": "已检测到 Aider 安装，拥有强大的代码行级精准重构和测试执行能力。" if aider_installed else "未能在 PATH 中寻找到 aider 可执行文件。",
        "suggested_prompt_addon": "本地已部署 Aider 结对编程专家，生成代码时可由 Aider 进行精准的代码集成与 Git 自动提交。",
        "suggested_tool": {
            "id": "aider_git_pair",
            "name": "Aider 结对编程",
            "icon": "🧙‍♂️",
            "description": "利用 Aider 对项目源文件执行全自动的 Git 修改跟踪与质量对齐工作。"
        }
    })

    return detected
