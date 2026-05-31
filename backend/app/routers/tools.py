"""Tool listing and testing endpoints."""
from fastapi import APIRouter
from app.agents.custom import AVAILABLE_TOOLS

router = APIRouter()


@router.get("/tools")
async def list_available_tools():
    """List prompt-addon tools (for custom agent builder UI)."""
    return [
        {"id": tid, "name": t["name"], "icon": t["icon"], "description": t["description"]}
        for tid, t in AVAILABLE_TOOLS.items()
    ]


@router.get("/runtime-tools")
async def list_runtime_tools():
    """List all registered executable runtime tools."""
    from app.tools import list_tools as _list_tools
    return _list_tools()


@router.post("/runtime-tools/{tool_name}/test")
async def test_runtime_tool(tool_name: str, body: dict = {}):
    """Manually test an executable tool with given params."""
    from app.tools import execute_tool_call
    result = await execute_tool_call(tool_name, body)
    return {
        "tool": tool_name,
        "success": result.success,
        "data": result.data,
        "error": result.error,
        "usage": result.usage,
    }


@router.post("/runtime-tools/{tool_name}/toggle")
async def toggle_runtime_tool(tool_name: str):
    """Enable/disable a runtime tool."""
    from app.tools import get_tool
    tool = get_tool(tool_name)
    if not tool:
        return {"error": f"Tool not found: {tool_name}"}
    tool.enabled = not tool.enabled
    return {"tool": tool_name, "enabled": tool.enabled}
