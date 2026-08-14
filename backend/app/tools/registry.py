"""AgentTool base class and runtime tool registry.

This module provides executable tools that Agents can invoke during generation
via the [tool_call:name]{params}[/tool_call] protocol.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

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
    parameters: dict  # JSON Schema for parameters (must be declared by subclasses)
    enabled: bool = True
    params_model: type[BaseModel] | None = None

    @abstractmethod
    async def execute(self, params: dict) -> ToolResult:
        """Execute the tool with given parameters.

        Args:
            params: dict matching self.parameters schema

        Returns:
            ToolResult with success/data/error
        """
        ...

    async def validate_and_execute(self, params: dict) -> ToolResult:
        """Validate input parameters using Pydantic model (if specified) and execute tool."""
        if self.params_model:
            from pydantic import ValidationError
            try:
                # Instantiate and validate using Pydantic model
                model_inst = self.params_model(**params)
                # Convert validated model back to dict for execute (compatible with existing signature)
                params = model_inst.model_dump()
            except ValidationError as ve:
                logger.warning(f"Parameter validation failed for tool '{self.name}': {ve}")
                return ToolResult(
                    success=False,
                    error=f"【参数强校验失败】调用工具 '{self.name}' 参数不合规，错误详情: {ve}"
                )
            except Exception as e:
                return ToolResult(success=False, error=f"参数校验异常: {e}")
        return await self.execute(params)

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
TENANT_TOOL_REGISTRY: dict[str, dict[str, AgentTool]] = {}


def register_tool(tool: AgentTool):
    """Register a tool instance globally."""
    TOOL_REGISTRY[tool.name] = tool
    logger.info(f"Registered tool: {tool.name}")


def register_tenant_tool(tenant_id: str, tool: AgentTool):
    TENANT_TOOL_REGISTRY.setdefault(tenant_id, {})[tool.name] = tool
    logger.info("Registered tenant tool %s for %s", tool.name, tenant_id)


def unregister_tenant_tools(tenant_id: str, names: set[str]) -> None:
    registry = TENANT_TOOL_REGISTRY.get(tenant_id, {})
    for name in names:
        registry.pop(name, None)


def get_tool(name: str) -> AgentTool | None:
    from app.core.tenancy import current_tenant_id

    tenant_id = current_tenant_id()
    if tenant_id and name in TENANT_TOOL_REGISTRY.get(tenant_id, {}):
        return TENANT_TOOL_REGISTRY[tenant_id][name]
    return TOOL_REGISTRY.get(name)


def is_tool_enabled(name: str, tool: AgentTool | None = None) -> bool:
    from app.core.tenancy import current_tenant_id
    from app.core.tenant_config import get_tenant_json

    tool = tool or get_tool(name)
    if tool is None or not tool.enabled:
        return False
    tenant_id = current_tenant_id()
    if not tenant_id:
        return True
    states = get_tenant_json(tenant_id, "runtime_tools", {}) or {}
    return states.get(name, True)


def list_tools() -> list[dict]:
    """List all registered tools as dicts."""
    from app.core.tenancy import current_tenant_id

    tools = dict(TOOL_REGISTRY)
    tenant_id = current_tenant_id()
    if tenant_id:
        tools.update(TENANT_TOOL_REGISTRY.get(tenant_id, {}))
    result = []
    for name, tool in tools.items():
        item = tool.to_dict()
        item["enabled"] = is_tool_enabled(name, tool)
        result.append(item)
    return result


def get_tools_prompt(tool_names: list[str] | None = None) -> str:
    """Build the tools instruction block for system prompt injection.

    Args:
        tool_names: if provided, only include these tools; else include all enabled
    """
    tools = []
    tools_for_tenant = {item["name"]: get_tool(item["name"]) for item in list_tools()}
    for name, tool in tools_for_tenant.items():
        if tool is None or not is_tool_enabled(name, tool):
            continue
        if tool_names is not None and name not in tool_names:
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
    if not is_tool_enabled(tool_name, tool):
        return ToolResult(success=False, error=f"工具已禁用: {tool_name}")

    from app.core.metrics import active_step_var
    step = active_step_var.get()
    span = None
    if step:
        span = step.start_span(
            name=f"tool_{tool_name}",
            span_type="tool",
            input_data={"params": params}
        )

    try:
        res = await tool.validate_and_execute(params)
        if span:
            span.finish(
                output_data={"success": res.success, "data": res.data, "error": res.error},
                status="success" if res.success else "error"
            )
        return res
    except Exception as e:
        logger.error(f"Tool '{tool_name}' execution error: {e}")
        if span:
            span.finish(
                output_data={"success": False, "error": str(e)},
                status="error"
            )
        return ToolResult(success=False, error=str(e))
