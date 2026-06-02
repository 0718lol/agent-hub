"""Tools package — JudgeTool protocol and AgentTool runtime tools."""

# Import tool modules to trigger auto-registration
from . import (
    block_editor_tools,  # noqa: F401
    browser_tools,  # noqa: F401
    code_agent_tools,  # noqa: F401
    code_interpreter_tools,  # noqa: F401
    file_ops,  # noqa: F401
    http_request,  # noqa: F401
    stateful_terminal_tool,  # noqa: F401
    web_search,  # noqa: F401
)
from .registry import (  # noqa: F401
    TOOL_REGISTRY,
    AgentTool,
    ToolResult,
    execute_tool_call,
    get_tool,
    get_tools_prompt,
    list_tools,
    parse_tool_calls,
    register_tool,
)
