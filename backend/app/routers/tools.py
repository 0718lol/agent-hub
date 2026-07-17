"""Tool listing and testing endpoints."""
import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.agents.custom import AVAILABLE_TOOLS
from app.core.tenancy import request_user_id
from app.core.tenant_settings import get_tenant_disabled_tools, save_tenant_disabled_tools


class ToolTestRequest(BaseModel):
    params: dict = Field(default_factory=dict, description="Parameters to pass to the tool")


class ToolToggleResponse(BaseModel):
    tool: str
    enabled: bool


router = APIRouter()
_tool_toggle_lock = asyncio.Lock()


@router.get("/tools")
async def list_available_tools():
    """List prompt-addon tools (for custom agent builder UI)."""
    return [
        {"id": tid, "name": t["name"], "icon": t["icon"], "description": t["description"]}
        for tid, t in AVAILABLE_TOOLS.items()
    ]


@router.get("/runtime-tools")
async def list_runtime_tools(request: Request):
    """List all registered executable runtime tools."""
    from app.tools.registry import list_tools as _list_tools
    from app.tools.registry import reset_tool_tenant, set_tool_tenant
    user_id = request_user_id(request)
    await asyncio.to_thread(get_tenant_disabled_tools, user_id)
    token = set_tool_tenant(user_id)
    try:
        return _list_tools()
    finally:
        reset_tool_tenant(token)


@router.post("/runtime-tools/{tool_name}/test")
async def test_runtime_tool(tool_name: str, request: Request, body: ToolTestRequest = ToolTestRequest()):
    """Manually test an executable tool with given params."""
    from app.tools.registry import execute_tool_call, reset_tool_tenant, set_tool_tenant
    user_id = request_user_id(request)
    await asyncio.to_thread(get_tenant_disabled_tools, user_id)
    token = set_tool_tenant(user_id)
    try:
        result = await execute_tool_call(tool_name, body.params)
    finally:
        reset_tool_tenant(token)
    return {
        "tool": tool_name,
        "success": result.success,
        "data": result.data,
        "error": result.error,
        "usage": result.usage,
    }


@router.post("/runtime-tools/{tool_name}/toggle")
async def toggle_runtime_tool(tool_name: str, request: Request):
    """Enable/disable a runtime tool for the current tenant."""
    from app.tools import get_tool
    tool = get_tool(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")
    user_id = request_user_id(request)
    async with _tool_toggle_lock:
        disabled = set(await asyncio.to_thread(get_tenant_disabled_tools, user_id))
        if tool_name in disabled:
            disabled.remove(tool_name)
        else:
            disabled.add(tool_name)
        await asyncio.to_thread(save_tenant_disabled_tools, user_id, disabled)
    return {"tool": tool_name, "enabled": tool.enabled and tool_name not in disabled}
