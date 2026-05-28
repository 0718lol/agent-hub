"""Tools package — JudgeTool protocol and AgentTool runtime tools."""

from .registry import (  # noqa: F401
    AgentTool, ToolResult, TOOL_REGISTRY,
    register_tool, get_tool, list_tools, get_tools_prompt,
    parse_tool_calls, execute_tool_call,
)

# Import tool modules to trigger auto-registration
from . import web_search  # noqa: F401
from . import http_request  # noqa: F401
from . import file_ops  # noqa: F401
from . import code_agent_tools  # noqa: F401
