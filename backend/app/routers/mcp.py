from fastapi import APIRouter
from pydantic import BaseModel
from app.core.mcp_bridge import mcp_bridge_manager

router = APIRouter(tags=["mcp"])


class MCPServerRegister(BaseModel):
    name: str
    command: str
    args: list[str] = []


@router.get("/mcp/servers")
async def list_mcp_servers():
    """List all registered MCP servers and their available tool namespaced schemas."""
    return await mcp_bridge_manager.get_servers_status()


@router.post("/mcp/servers")
async def register_mcp_server(body: MCPServerRegister):
    """Dynamically launch and connect to a new stdio JSON-RPC MCP server."""
    success = await mcp_bridge_manager.register_server(
        name=body.name,
        command=body.command,
        args=body.args
    )
    if success:
        return {"status": "ok", "message": f"MCP server '{body.name}' launched successfully."}
    return {"status": "error", "message": "Failed to connect to MCP server."}


@router.post("/mcp/servers/{server_name}/toggle")
async def toggle_mcp_server(server_name: str, enabled: bool):
    """Temporarily suspend or reactivate an active MCP server."""
    success = await mcp_bridge_manager.toggle_server(server_name, enabled)
    if success:
        return {"status": "ok", "message": f"Server status updated."}
    return {"status": "error", "message": "Failed to toggle server state."}


@router.delete("/mcp/servers/{server_name}")
async def unregister_mcp_server(server_name: str):
    """Stop child stdio processes and permanently unregister MCP server."""
    success = await mcp_bridge_manager.unregister_server(server_name)
    if success:
        return {"status": "ok", "message": f"MCP Server '{server_name}' successfully stopped."}
    return {"status": "error", "message": "Server not found."}
