import re
import shlex

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.mcp_bridge import mcp_bridge_manager
from app.core.tenancy import request_user_id

ALLOWED_MCP_COMMANDS = {"npx", "node", "python", "uvx"}

# Dangerous args patterns that could enable code execution
_DANGEROUS_ARG_PATTERNS = [
    re.compile(r'^-c$'),                          # python -c "code"
    re.compile(r'^--command$'),                    # various --command flags
    re.compile(r'^-e$'),                           # python -e / node -e
    re.compile(r'^--eval$'),                       # node --eval
    re.compile(r'^--require$'),                    # node -r / --require (preload modules)
]

_MAX_ARG_LENGTH = 1024

router = APIRouter(tags=["mcp"])


class MCPServerRegister(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    command: str
    args: list[str] = Field(default_factory=list, max_length=64)


@router.get("/mcp/servers")
async def list_mcp_servers(request: Request):
    """List all registered MCP servers and their available tool namespaced schemas."""
    return await mcp_bridge_manager.get_servers_status(request_user_id(request))


@router.post("/mcp/servers")
async def register_mcp_server(body: MCPServerRegister, request: Request):
    """Dynamically launch and connect to a new stdio JSON-RPC MCP server."""
    parts = shlex.split(body.command) if body.command.strip() else []
    cmd_base = parts[0] if parts else ""
    if cmd_base not in ALLOWED_MCP_COMMANDS:
        return {"status": "error", "message": f"Command '{cmd_base}' not allowed. Allowed: {ALLOWED_MCP_COMMANDS}"}

    # Validate command field itself: block shell metacharacters
    _SHELL_META = re.compile(r'[;&|`$(){}!<>]')
    if _SHELL_META.search(body.command):
        return {"status": "error", "message": "Command field contains forbidden shell metacharacters"}

    # Validate each arg: length limit + shell metacharacter check
    for i, arg in enumerate(body.args):
        if len(arg) > _MAX_ARG_LENGTH:
            return {"status": "error", "message": f"Arg[{i}] exceeds max length ({_MAX_ARG_LENGTH} chars)"}
        if _SHELL_META.search(arg):
            return {"status": "error", "message": f"Args contain forbidden shell metacharacters: {arg}"}

    # Cross-validation: block dangerous arg patterns for python/node interpreters
    # Prevent: python -c "import os; os.system(...)" or node -e "require('child_process')..."
    if cmd_base in ("python", "node", "npx", "uvx"):
        for _, arg in enumerate(body.args):
            for pattern in _DANGEROUS_ARG_PATTERNS:
                if pattern.match(arg):
                    return {"status": "error", "message": f"Dangerous arg pattern '{arg}' not allowed for '{cmd_base}'"}

    success = await mcp_bridge_manager.register_server(
        tenant_id=request_user_id(request),
        name=body.name,
        command=body.command,
        args=body.args
    )
    if success:
        return {"status": "ok", "message": f"MCP server '{body.name}' launched successfully."}
    return {"status": "error", "message": "Failed to connect to MCP server."}


@router.post("/mcp/servers/{server_name}/toggle")
async def toggle_mcp_server(server_name: str, enabled: bool, request: Request):
    """Temporarily suspend or reactivate an active MCP server."""
    success = await mcp_bridge_manager.toggle_server(request_user_id(request), server_name, enabled)
    if success:
        return {"status": "ok", "message": "Server status updated."}
    return {"status": "error", "message": "Failed to toggle server state."}


@router.delete("/mcp/servers/{server_name}")
async def unregister_mcp_server(server_name: str, request: Request):
    """Stop child stdio processes and permanently unregister MCP server."""
    success = await mcp_bridge_manager.unregister_server(request_user_id(request), server_name)
    if success:
        return {"status": "ok", "message": f"MCP Server '{server_name}' successfully stopped."}
    return {"status": "error", "message": "Server not found."}
