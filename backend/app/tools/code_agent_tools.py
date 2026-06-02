"""Safe Python Executor Tool — restricted Python execution sandbox for agents."""

import logging
import json
from .registry import AgentTool, ToolResult, register_tool, execute_tool_call
from app.core.ast_interpreter import SafeASTInterpreter
from app.core.mcp_client import mcp_manager

logger = logging.getLogger("tool_code_agent_tools")

class SafePythonExecutorTool(AgentTool):
    name = "safe_python_executor"
    description = "安全执行 Python 脚本，以单步自愈和自校验的方式批量读写文件及运行测试"
    icon = "🛡️"
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "要执行的 Python 代码脚本，允许使用 for 循环、if 判断及 allowed 工具函数。",
            },
            "conversation_id": {
                "type": "string",
                "description": "对话 ID（自动注入）",
            },
        },
        "required": ["code"],
    }

    async def execute(self, params: dict) -> ToolResult:
        code = params.get("code", "").strip()
        conv_id = params.get("conversation_id", "default")

        if not code:
            return ToolResult(success=False, error="执行代码不能为空")

        # Define the sandboxed methods that map to system MCP and registry tools
        async def file_read(path: str) -> str:
            res = await mcp_manager.execute_tool("SystemServer__workspace_read_file", {"path": path}, conv_id)
            if res.get("isError"):
                raise IOError(res["content"][0]["text"])
            return res["content"][0]["text"]

        async def file_write(path: str, content: str) -> str:
            res = await mcp_manager.execute_tool("SystemServer__workspace_write_file", {"path": path, "content": content}, conv_id)
            if res.get("isError"):
                raise IOError(res["content"][0]["text"])
            return res["content"][0]["text"]

        async def file_list(path: str = ".") -> list:
            res = await mcp_manager.execute_tool("SystemServer__workspace_list_dir", {"path": path}, conv_id)
            if res.get("isError"):
                raise IOError(res["content"][0]["text"])
            try:
                return json.loads(res["content"][0]["text"])
            except Exception:
                return res["content"][0]["text"]

        async def run_command(command: str) -> str:
            res = await mcp_manager.execute_tool("SystemServer__workspace_run_command", {"command": command}, conv_id)
            if res.get("isError"):
                raise RuntimeError(res["content"][0]["text"])
            return res["content"][0]["text"]

        async def web_search(query: str) -> dict:
            res = await execute_tool_call("web_search", {"query": query})
            if not res.success:
                raise RuntimeError(res.error)
            return res.data

        async def http_request(url: str, method: str = "GET", headers: dict = None, json_data: dict = None) -> dict:
            p = {
                "url": url,
                "method": method,
                "headers": headers or {},
                "json_data": json_data or {}
            }
            res = await execute_tool_call("http_request", p)
            if not res.success:
                raise RuntimeError(res.error)
            return res.data

        # Build allowed tools map for AST execution context
        allowed_tools = {
            "file_read": file_read,
            "file_write": file_write,
            "file_list": file_list,
            "run_command": run_command,
            "web_search": web_search,
            "http_request": http_request
        }

        # Initialize safe interpreter and run
        interpreter = SafeASTInterpreter(allowed_tools=allowed_tools)
        run_res = await interpreter.execute(code)
        
        if not run_res["success"]:
            return ToolResult(
                success=False,
                error=run_res["error"],
                data={"stdout": run_res["stdout"], "result": run_res["result"]}
            )

        return ToolResult(
            success=True,
            data={
                "stdout": run_res["stdout"],
                "result": run_res["result"],
                "message": "代码安全沙箱运行成功"
            }
        )

# Auto-register on import
register_tool(SafePythonExecutorTool())
