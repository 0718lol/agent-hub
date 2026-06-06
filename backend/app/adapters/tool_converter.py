"""Tool Converter — 工具定义格式转换器。

将自研 AgentTool 格式转换为各平台所需的工具定义格式：
- Claude: Anthropic tool_use format
- Codex/OpenAI: function calling format
- Coze: plugin format
- 自部署: 通用 JSON Schema format
"""

import logging
from typing import Any

logger = logging.getLogger("tool_converter")


def supports_tool_calling(model: str = "", api_url: str = "") -> bool:
    """探测 API 是否支持工具调用（function calling / tool_use）。

    基于模型名和 API 地址的启发式判断：
    - Claude 系列：所有模型都支持 tool_use
    - OpenAI：gpt-4o, gpt-4-turbo, gpt-3.5-turbo 等支持
    - DeepSeek：deepseek-chat, deepseek-reasoner 支持
    - Qwen：qwen-plus, qwen-turbo, qwen-max 支持
    - 其他：默认不支持，需要用户手动选择 agent 模式
    """
    m = (model or "").lower()
    u = (api_url or "").lower()

    # Claude 系列
    if "claude" in m or "anthropic" in u:
        return True

    # OpenAI 系列
    if any(k in m for k in ("gpt-4o", "gpt-4-turbo", "gpt-4-1106", "gpt-3.5-turbo", "o1", "o3")):
        return True
    if "openai" in u:
        return True

    # DeepSeek
    if "deepseek" in m:
        return True

    # Qwen / 通义千问
    if any(k in m for k in ("qwen-plus", "qwen-turbo", "qwen-max", "qwen-long")):
        return True

    # 未知模型，不支持
    return False


def get_project_tools(enabled_tools: list[str] = None) -> list[dict]:
    """获取项目中已注册的工具，返回原始定义。"""
    try:
        from app.tools.registry import _tools
        tools = []
        for name, tool in _tools.items():
            if enabled_tools and name not in enabled_tools:
                continue
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters or {},
            })
        return tools
    except Exception as e:
        logger.warning(f"Failed to get project tools: {e}")
        return []


def to_claude_tools(tools: list[dict]) -> list[dict]:
    """转换为 Anthropic Claude tool_use 格式。

    输入: [{"name": "...", "description": "...", "parameters": {schema}}]
    输出: [{"name": "...", "description": "...", "input_schema": {schema}}]
    """
    return [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
        }
        for t in tools
    ]


def to_openai_tools(tools: list[dict]) -> list[dict]:
    """转换为 OpenAI function calling 格式。

    输入: [{"name": "...", "description": "...", "parameters": {schema}}]
    输出: [{"type": "function", "function": {"name": "...", ...}}]
    """
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


def to_coze_tools(tools: list[dict]) -> list[dict]:
    """转换为 Coze 插件格式。

    输入: [{"name": "...", "description": "...", "parameters": {schema}}]
    输出: [{"type": "function", "function": {"name": "...", ...}}]
    (Coze 使用与 OpenAI 兼容的格式)
    """
    return to_openai_tools(tools)


def to_generic_tools(tools: list[dict]) -> list[dict]:
    """转换为通用格式（自部署 Agent 使用）。

    输入: [{"name": "...", "description": "...", "parameters": {schema}}]
    输出: 原样返回
    """
    return tools


def parse_claude_tool_use(content_blocks: list[dict]) -> list[dict]:
    """解析 Claude 响应中的 tool_use 块。

    输入: Anthropic response.content 数组
    输出: [{"name": "...", "input": {...}}]
    """
    tool_calls = []
    for block in content_blocks:
        if block.get("type") == "tool_use":
            tool_calls.append({
                "name": block["name"],
                "input": block.get("input", {}),
            })
    return tool_calls


def parse_openai_tool_calls(tool_calls: list[dict]) -> list[dict]:
    """解析 OpenAI 响应中的 tool_calls。

    输入: response.choices[0].message.tool_calls 数组
    输出: [{"name": "...", "arguments": {...}}]
    """
    import json
    result = []
    for tc in tool_calls:
        func = tc.get("function", {})
        args = func.get("arguments", "{}")
        try:
            args = json.loads(args) if isinstance(args, str) else args
        except json.JSONDecodeError:
            args = {}
        result.append({
            "name": func.get("name", ""),
            "arguments": args,
        })
    return result


async def execute_tool(tool_name: str, tool_params: dict) -> dict:
    """执行项目中的工具，返回统一结果格式。"""
    try:
        from app.tools.registry import execute_tool_call
        result = await execute_tool_call(tool_name, tool_params)
        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
        }
    except Exception as e:
        return {"success": False, "data": None, "error": str(e)}
