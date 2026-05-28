"""Stateful Terminal Tool — executes shell commands within persistent terminal sessions."""

import os
import logging
from .registry import AgentTool, ToolResult, register_tool
from app.core.terminal import stateful_terminal_manager

logger = logging.getLogger("tool_stateful_terminal")

class StatefulTerminalTool(AgentTool):
    name = "run_stateful_command"
    description = "在物理沙盒工作空间内持久地、有状态地执行指定的 Shell 命令行，支持多步环境状态继承"
    icon = "💻"
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的命令行指令（例如 'cd frontend', 'ls', 'pytest'，必填）",
            },
            "conversation_id": {
                "type": "string",
                "description": "对话 ID（自动注入）",
            },
        },
        "required": ["command"],
    }

    async def execute(self, params: dict) -> ToolResult:
        command = params.get("command", "").strip()
        conv_id = params.get("conversation_id", "default")

        if not command:
            return ToolResult(success=False, error="命令行指令不能为空")

        # Resolve current physical sandbox directory
        workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        sandbox_dir = os.path.join(workspace_dir, "agenthub_export", conv_id)
        os.makedirs(sandbox_dir, exist_ok=True)

        try:
            # 1. Fetch or create persistent terminal session
            terminal = await stateful_terminal_manager.get_or_create_session(conv_id, sandbox_dir)

            # 2. Exec command statefully
            logger.info(f"[StatefulTerminalTool] Executing command for {conv_id}: {command}")
            output = await terminal.execute(command)

            return ToolResult(
                success=True,
                data={
                    "command": command,
                    "output": output,
                    "message": "命令行执行完成"
                }
            )
        except Exception as e:
            logger.error(f"[StatefulTerminalTool] Execution failed: {e}")
            return ToolResult(success=False, error=f"有状态命令行执行异常: {str(e)}")

# Auto-register on import
register_tool(StatefulTerminalTool())
