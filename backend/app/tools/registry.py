"""AgentTool base class and runtime tool registry.

This module provides executable tools that Agents can invoke during generation
via the [tool_call:name]{params}[/tool_call] protocol.
"""

import json
import re
import logging
from dataclasses import dataclass, field
from typing import Any
from abc import ABC, abstractmethod

logger = logging.getLogger("tool_registry")


@dataclass
class ToolResult:
    """Standard result from any AgentTool execution."""
    success: bool
    data: Any = None
    error: str = ""
    usage: dict = field(default_factory=dict)  # e.g. {"tokens": 0, "time_ms": 123}


class AgentTool(ABC):
    """Base class for all executable agent tools."""

    name: str = ""
    description: str = ""
    icon: str = "🔧"
    parameters: dict = {}  # JSON Schema for parameters
    enabled: bool = True

    @abstractmethod
    async def execute(self, params: dict) -> ToolResult:
        """Execute the tool with given parameters.

        Args:
            params: dict matching self.parameters schema

        Returns:
            ToolResult with success/data/error
        """
        ...

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "parameters": self.parameters,
            "enabled": self.enabled,
        }

    def get_prompt_description(self) -> str:
        """Generate prompt text describing this tool for the Agent."""
        params_desc = ""
        props = self.parameters.get("properties", {})
        if props:
            parts = []
            for k, v in props.items():
                req = "必填" if k in self.parameters.get("required", []) else "可选"
                parts.append(f"  - {k} ({v.get('type', 'string')}, {req}): {v.get('description', '')}")
            params_desc = "\n".join(parts)
        return f"- **{self.name}**: {self.description}\n  参数:\n{params_desc}"


# ---- Global Tool Registry ----
TOOL_REGISTRY: dict[str, AgentTool] = {}


def register_tool(tool: AgentTool):
    """Register a tool instance globally."""
    TOOL_REGISTRY[tool.name] = tool
    logger.info(f"Registered tool: {tool.name}")


def get_tool(name: str) -> AgentTool | None:
    return TOOL_REGISTRY.get(name)


def list_tools() -> list[dict]:
    """List all registered tools as dicts."""
    return [t.to_dict() for t in TOOL_REGISTRY.values()]


def get_tools_prompt(tool_names: list[str] | None = None) -> str:
    """Build the tools instruction block for system prompt injection.

    Args:
        tool_names: if provided, only include these tools; else include all enabled
    """
    tools = []
    for name, tool in TOOL_REGISTRY.items():
        if not tool.enabled:
            continue
        if tool_names and name not in tool_names:
            continue
        tools.append(tool)

    if not tools:
        return ""

    lines = [
        "\n\n【可用工具】你可以通过以下格式调用工具：",
        '[tool_call:工具名]{"参数名": "值"}[/tool_call]',
        "",
        "系统会自动执行工具并将结果返回给你，你再基于结果继续回复用户。",
        "",
        "可用工具列表：",
    ]
    for tool in tools:
        lines.append(tool.get_prompt_description())
    lines.append("")
    lines.append("注意：每次只调用一个工具，等待结果后再决定下一步。")
    return "\n".join(lines)


# ---- Tool Call Parsing ----
TOOL_CALL_PATTERN = re.compile(
    r'\[tool_call:(\w+)\](.*?)\[/tool_call\]',
    re.DOTALL
)


def parse_tool_calls(text: str) -> list[tuple[str, dict, int, int]]:
    """Parse tool_call tags from agent output.

    Returns list of (tool_name, params_dict, start_pos, end_pos).
    """
    results = []
    for match in TOOL_CALL_PATTERN.finditer(text):
        tool_name = match.group(1)
        params_raw = match.group(2).strip()
        try:
            params = json.loads(params_raw) if params_raw else {}
        except json.JSONDecodeError:
            params = {"raw": params_raw}
        results.append((tool_name, params, match.start(), match.end()))
    return results


async def execute_tool_call(tool_name: str, params: dict) -> ToolResult:
    """Execute a tool by name with given params."""
    tool = get_tool(tool_name)
    if not tool:
        return ToolResult(success=False, error=f"未知工具: {tool_name}")
    if not tool.enabled:
        return ToolResult(success=False, error=f"工具已禁用: {tool_name}")
    try:
        return await tool.execute(params)
    except Exception as e:
        logger.error(f"Tool '{tool_name}' execution error: {e}")
        return ToolResult(success=False, error=str(e))
