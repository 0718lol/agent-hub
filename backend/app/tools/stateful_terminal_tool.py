"""Compatibility terminal tool backed by the isolated sandbox manager."""

import logging

from app.core.config import settings
from app.core.sandbox_manager import sandbox_manager
from app.core.workspace import resolve_workspace

from .registry import AgentTool, ToolResult, register_tool

logger = logging.getLogger("tool_stateful_terminal")


class StatefulTerminalTool(AgentTool):
    name = "run_stateful_command"
    description = "在生成项目的只读隔离副本中执行 Shell 命令，可运行 npm、pytest 等检查"
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
        if not command:
            return ToolResult(success=False, error="命令行指令不能为空")

        conversation_id = str(params.get("conversation_id") or "default")
        workspace = resolve_workspace(conversation_id, create=False)
        if workspace is None:
            return ToolResult(success=False, error="对话 ID 非法")
        if not workspace.is_dir():
            return ToolResult(success=False, error="当前对话还没有生成项目，无法运行项目命令")

        try:
            result = await sandbox_manager.execute(
                command,
                language="shell",
                timeout=settings.runtime_sandbox_timeout,
                workspace=workspace,
                quota_key=conversation_id,
            )
            if result.get("status") != "success":
                return ToolResult(success=False, error=result.get("stderr") or "隔离命令执行失败")
            return ToolResult(
                success=True,
                data={
                    "command": command,
                    "output": result.get("stdout", ""),
                    "exit_code": result.get("exit_code", 0),
                    "message": "隔离命令执行完成",
                }
            )
        except Exception as e:
            logger.error(f"[StatefulTerminalTool] Execution failed: {e}")
            return ToolResult(success=False, error=f"隔离命令行执行异常: {e!s}")

# Auto-register on import
register_tool(StatefulTerminalTool())
