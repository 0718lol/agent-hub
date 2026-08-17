import asyncio
import json
import logging
import os
import sys
from typing import Any

from app.tools.registry import (
    AgentTool,
    ToolResult,
    register_tenant_tool,
    register_tool,
    unregister_tenant_tools,
)

logger = logging.getLogger("mcp_bridge")

# External MCP servers are separate programs. Do not leak the host process'
# credentials (LLM keys, API secret, cloud tokens, etc.) to them by default.
_MCP_BASE_ENV_KEYS = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "WINDIR")


def _build_mcp_environment(configured_env: dict[str, str] | None) -> dict[str, str]:
    env = {key: os.environ[key] for key in _MCP_BASE_ENV_KEYS if os.environ.get(key)}
    env["PYTHONIOENCODING"] = "utf-8"
    env.update({str(key): str(value) for key, value in (configured_env or {}).items()})
    return env

class MCPServerProcess:
    """Manages the life-cycle and communication of a single Stdio-based MCP Server process."""

    def __init__(self, name: str, command: str, args: list[str], env: dict[str, str] | None = None):
        self.name = name
        self.command = command
        self.args = args
        self.env = _build_mcp_environment(env)
        self.process: asyncio.subprocess.Process = None
        self.rpc_id = 1
        self.pending_requests: dict[int, asyncio.Future] = {}
        self.listen_task: asyncio.Task = None
        self.error_task: asyncio.Task = None
        self._running = False

    async def start(self):
        """Start the MCP Server process and set up communication pipes."""
        logger.info(f"Starting MCP Server process [{self.name}]: {self.command} {' '.join(self.args)}")

        # Ensure executable resolution is robust on Windows
        cmd = self.command
        if sys.platform == "win32" and cmd in ("npm", "npx", "npx.cmd", "npm.cmd"):
            shell = True
        else:
            shell = False

        try:
            if shell:
                full_cmd = f"{cmd} " + " ".join(f'"{a}"' for a in self.args)
                self.process = await asyncio.create_subprocess_shell(
                    full_cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=self.env
                )
            else:
                self.process = await asyncio.create_subprocess_exec(
                    cmd,
                    *self.args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=self.env
                )
        except Exception as e:
            logger.error(f"Failed to launch MCP Server process [{self.name}]: {e}")
            raise e

        self._running = True
        self.listen_task = asyncio.create_task(self._listen_stdout())
        self.error_task = asyncio.create_task(self._listen_stderr())
        logger.info(f"MCP Server process [{self.name}] started successfully (PID: {self.process.pid})")

    async def stop(self):
        """Gracefully terminate the MCP Server process."""
        if not self._running and not self.process:
            self._fail_pending("MCP Server connection terminated.")
            return
        self._running = False
        logger.info(f"Stopping MCP Server process [{self.name}]...")

        self._fail_pending("MCP Server connection terminated.")

        if self.listen_task:
            self.listen_task.cancel()
        if self.error_task:
            self.error_task.cancel()

        if self.process and self.process.returncode is None:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except TimeoutError:
                logger.warning(f"MCP Server [{self.name}] did not terminate gracefully. Killing it...")
                try:
                    self.process.kill()
                except Exception as e:
                    logger.warning(f"Failed to kill MCP server process [{self.name}]: {e}")
            except Exception as e:
                logger.debug(f"Exception during terminating MCP Server process [{self.name}]: {e}")

        logger.info(f"MCP Server process [{self.name}] stopped.")

    def _fail_pending(self, message: str) -> None:
        """Resolve all outstanding RPCs when the process can no longer answer."""
        pending = list(self.pending_requests.values())
        self.pending_requests.clear()
        for fut in pending:
            if not fut.done():
                fut.set_exception(RuntimeError(message))

    async def list_tools(self) -> list[dict[str, Any]]:
        """Request the list of available tools from this MCP Server."""
        req_id = self.rpc_id
        self.rpc_id += 1

        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/list",
            "params": {}
        }

        fut = asyncio.get_running_loop().create_future()
        self.pending_requests[req_id] = fut

        try:
            await self._write_stdin(payload)
            response = await fut
            return response.get("tools", [])
        except Exception as e:
            logger.error(f"Error querying tools list from MCP Server [{self.name}]: {e}")
            raise e

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a specific tool on this MCP Server."""
        req_id = self.rpc_id
        self.rpc_id += 1

        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        fut = asyncio.get_running_loop().create_future()
        self.pending_requests[req_id] = fut

        try:
            await self._write_stdin(payload)
            result = await fut
            return result
        except Exception as e:
            logger.error(f"Error calling tool [{tool_name}] on MCP Server [{self.name}]: {e}")
            raise e

    async def _write_stdin(self, payload: dict):
        if not self.process or not self.process.stdin:
            raise RuntimeError("Process stdin channel is closed.")
        data = (json.dumps(payload) + "\n").encode("utf-8")
        self.process.stdin.write(data)
        await self.process.stdin.drain()

    async def _listen_stdout(self):
        """Continuously parse and dispatch JSON-RPC responses from the process stdout."""
        while self._running and self.process and self.process.stdout:
            try:
                line = await self.process.stdout.readline()
                if not line:
                    self._running = False
                    self._fail_pending("MCP Server process closed its stdout.")
                    break
                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue

                response = json.loads(line_str)
                req_id = response.get("id")
                if req_id is not None and req_id in self.pending_requests:
                    fut = self.pending_requests.pop(req_id)
                    if "error" in response:
                        err = response["error"]
                        fut.set_exception(RuntimeError(f"RPC Error [{err.get('code')}]: {err.get('message')}"))
                    else:
                        fut.set_result(response.get("result"))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error reading stdout from MCP Server [{self.name}]: {e}")
                await asyncio.sleep(0.1)

    async def _listen_stderr(self):
        """Log diagnostic/error outputs from the process stderr."""
        while self._running and self.process and self.process.stderr:
            try:
                line = await self.process.stderr.readline()
                if not line:
                    break
                line_str = line.decode("utf-8").strip()
                if line_str:
                    logger.warning(f"[{self.name} (stderr)]: {line_str}")
            except asyncio.CancelledError:
                break
            except Exception:
                break


class BuiltinMCPServer:
    """In-memory System-level Builtin MCP Server exposing HIL tools and sandbox Repo Map resource safely."""

    def __init__(self):
        self.name = "system-builtin"

    async def list_tools(self) -> list[dict[str, Any]]:
        """Expose standard interactive HIL Tool details."""
        return [
            {
                "name": "user_interaction_judge",
                "description": "人工交互评测与异步协同 HIL 拦截工具，提示用户进行方案选择、反馈或一键审批。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "需要询问用户的问题或修改方案的文字详情"
                        },
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "供用户选择的快捷动作列表，例如 ['*Approve::批准', 'Terminate::终止']"
                        },
                        "conversation_id": {
                            "type": "string",
                            "description": "当前交互关联的会话 ID"
                        }
                    },
                    "required": ["question", "conversation_id"]
                }
            }
        ]

    async def list_resources(self) -> list[dict[str, Any]]:
        """Expose Project Codebase Skeleton (Repo Map) as read-only standard MCP Resource."""
        return [
            {
                "uri": "workspace://repomap",
                "name": "Project Codebase Outline Map",
                "description": "AST-based compact structural outline maps of all classes, methods and signatures inside the workspace sandbox.",
                "mimeType": "text/markdown"
            }
        ]

    def read_resource_sync(self, uri: str, conversation_id: str | None = None) -> str:
        """Standard synchronous implementation to read the content of the specified workspace resource URI."""
        if uri == "workspace://repomap":
            from app.core.repo_map import codebase_map_scanner
            # Pick workspace sandbox directory safely
            workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            if conversation_id:
                if ".." in conversation_id or "/" in conversation_id or "\\" in conversation_id:
                    raise ValueError("Invalid conversation_id")
                sandbox_dir = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "agenthub_export", conversation_id)
                if os.path.exists(sandbox_dir):
                    workspace_dir = sandbox_dir

            logger.info(f"MCP Resource workspace://repomap called (Sync). Scanning workspace path: {workspace_dir}")
            return codebase_map_scanner.scan_directory(workspace_dir)

        raise ValueError(f"Unknown Resource URI: {uri}")

    async def read_resource(self, uri: str, conversation_id: str | None = None) -> str:
        """Standard asynchronous wrapper to read resource."""
        return self.read_resource_sync(uri, conversation_id)

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Route tool calls internally to the concrete UserInteractionJudgeTool implementation."""
        if tool_name == "user_interaction_judge":
            from app.tools.judge_tools import UserInteractionJudgeTool
            tool = UserInteractionJudgeTool()
            res = await tool.run(arguments)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Decision: {res.decision}\nReason: {res.reason}\nAnswer: {res.signals.get('answer', '')}"
                    }
                ],
                "isError": res.decision == "error"
            }
        raise ValueError(f"Unknown system builtin tool: {tool_name}")


class MCPToolWrapper(AgentTool):
    """Bridges an MCP tool dynamically into AgentHub's AgentTool standard architecture."""

    def __init__(self, server_name: str, mcp_client: Any, name: str, description: str, parameters: dict):
        self.server_name = server_name
        self.mcp_client = mcp_client
        self.name = name
        self.description = description
        self.parameters = parameters or {"type": "object", "properties": {}}
        self.icon = "🔌"

    async def execute(self, params: dict) -> ToolResult:
        try:
            logger.info(f"Routing tool call [{self.name}] to MCP Server [{self.server_name}] with params: {params}")
            raw_result = await self.mcp_client.call_tool(self.name, params)

            is_error = raw_result.get("isError", False)
            content_list = raw_result.get("content", [])
            text_outputs = []

            for item in content_list:
                if item.get("type") == "text":
                    text_outputs.append(item.get("text", ""))

            output_text = "\n".join(text_outputs)

            if is_error:
                return ToolResult(success=False, error=output_text or "MCP Tool execution failed.")
            return ToolResult(success=True, data=output_text)
        except Exception as e:
            logger.error(f"MCP Tool execution failed: {e}")
            return ToolResult(success=False, error=str(e))


class MCPBridgeManager:
    """Singleton registry manager to coordinate all external and builtin MCP Servers."""

    def __init__(self):
        self.servers: dict[str, MCPServerProcess] = {}
        self._tenant_servers: dict[str, dict[str, MCPServerProcess]] = {}
        self._server_tools: dict[tuple[str, str], set[str]] = {}
        self._tenant_locks: dict[str, asyncio.Lock] = {}
        self._loaded_tenants: set[str] = set()
        self.builtin_server = BuiltinMCPServer()

    def _servers_for(self, tenant_id: str) -> dict[str, MCPServerProcess]:
        if tenant_id == "legacy":
            return self.servers
        return self._tenant_servers.setdefault(tenant_id, {})

    async def _start_server(
        self,
        tenant_id: str,
        name: str,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> bool:
        servers = self._servers_for(tenant_id)
        existing = servers.get(name)
        if existing and existing._running:
            return True
        server = MCPServerProcess(name, command, args, env)
        try:
            await server.start()
            tools = await server.list_tools()
            tool_names: set[str] = set()
            for tool in tools:
                tool_name = tool.get("name")
                if not tool_name:
                    continue
                wrapper = MCPToolWrapper(
                    name,
                    server,
                    tool_name,
                    tool.get("description", ""),
                    tool.get("inputSchema", {}),
                )
                register_tenant_tool(tenant_id, wrapper)
                tool_names.add(tool_name)
            servers[name] = server
            self._server_tools[(tenant_id, name)] = tool_names
            return True
        except Exception as exc:
            logger.error("Failed to start MCP server %s for tenant %s: %s", name, tenant_id, exc)
            await server.stop()
            return False

    async def ensure_tenant_servers(self, tenant_id: str) -> None:
        if tenant_id in self._loaded_tenants:
            return
        lock = self._tenant_locks.setdefault(tenant_id, asyncio.Lock())
        async with lock:
            if tenant_id in self._loaded_tenants:
                return
            from app.core.tenant_config import get_tenant_json

            configs = get_tenant_json(tenant_id, "mcp_servers", {}, encrypted=True) or {}
            for name, config in configs.items():
                if config.get("enabled", True):
                    await self._start_server(
                        tenant_id,
                        name,
                        config.get("command", ""),
                        config.get("args", []),
                        config.get("env"),
                    )
            self._loaded_tenants.add(tenant_id)

    async def register_server(
        self,
        tenant_id: str,
        name: str,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> bool:
        await self.unregister_server(tenant_id, name, remove_config=False)
        success = await self._start_server(tenant_id, name, command, args, env)
        if success:
            from app.core.tenant_config import get_tenant_json, set_tenant_json

            configs = get_tenant_json(tenant_id, "mcp_servers", {}, encrypted=True) or {}
            configs[name] = {
                "command": command,
                "args": args,
                "env": env or {},
                "enabled": True,
            }
            set_tenant_json(tenant_id, "mcp_servers", configs, encrypted=True)
            self._loaded_tenants.add(tenant_id)
        return success

    async def get_servers_status(self, tenant_id: str) -> list[dict]:
        await self.ensure_tenant_servers(tenant_id)
        from app.core.tenant_config import get_tenant_json

        configs = get_tenant_json(tenant_id, "mcp_servers", {}, encrypted=True) or {}
        running = self._servers_for(tenant_id)
        return [
            {
                "name": name,
                "command": config.get("command", ""),
                "args": config.get("args", []),
                "enabled": config.get("enabled", True),
                "running": bool(running.get(name) and running[name]._running),
                "tool_count": len(self._server_tools.get((tenant_id, name), set())),
            }
            for name, config in sorted(configs.items())
        ]

    async def toggle_server(self, tenant_id: str, name: str, enabled: bool) -> bool:
        from app.core.tenant_config import get_tenant_json, set_tenant_json

        configs = get_tenant_json(tenant_id, "mcp_servers", {}, encrypted=True) or {}
        config = configs.get(name)
        if not config:
            return False
        if enabled:
            success = await self._start_server(
                tenant_id,
                name,
                config.get("command", ""),
                config.get("args", []),
                config.get("env"),
            )
            if not success:
                return False
        else:
            await self.unregister_server(tenant_id, name, remove_config=False)
        config["enabled"] = enabled
        configs[name] = config
        set_tenant_json(tenant_id, "mcp_servers", configs, encrypted=True)
        return True

    async def unregister_server(
        self,
        tenant_id: str,
        name: str,
        *,
        remove_config: bool = True,
    ) -> bool:
        servers = self._servers_for(tenant_id)
        server = servers.pop(name, None)
        names = self._server_tools.pop((tenant_id, name), set())
        unregister_tenant_tools(tenant_id, names)
        if server:
            await server.stop()
        if remove_config:
            from app.core.tenant_config import get_tenant_json, set_tenant_json

            configs = get_tenant_json(tenant_id, "mcp_servers", {}, encrypted=True) or {}
            existed = name in configs
            configs.pop(name, None)
            set_tenant_json(tenant_id, "mcp_servers", configs, encrypted=True)
            return bool(server or existed)
        return bool(server)

    async def load_and_start_servers(self, config_path: str):
        """Parse configuration, start all stdio servers, and mount the builtin in-memory server."""
        # 1. Mount and dynamic map Builtin Server's HIL tool
        try:
            builtin_tools = await self.builtin_server.list_tools()
            for t in builtin_tools:
                t_name = t.get("name")
                t_desc = t.get("description", "")
                t_schema = t.get("inputSchema", {})

                # Note: System builtins are placed into TOOL_REGISTRY with higher priority
                wrapper = MCPToolWrapper(self.builtin_server.name, self.builtin_server, t_name, t_desc, t_schema)
                register_tool(wrapper)
                logger.info(f"Dynamically mapped and registered Builtin System MCP tool: {t_name}")
        except Exception as e:
            logger.error(f"Failed to load Builtin system tools: {e}")

        # 2. Dynamically spawn external config-based stdio servers
        if not os.path.exists(config_path):
            logger.warning(f"MCP Configuration path not found: {config_path}. No external servers loaded.")
            return

        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read MCP config: {e}")
            return

        mcp_servers = config.get("mcpServers", {})
        for name, cfg in mcp_servers.items():
            command = cfg.get("command")
            args = cfg.get("args", [])
            env = cfg.get("env")

            if not command:
                logger.error(f"Skipping MCP Server [{name}]: command not specified.")
                continue

            server = MCPServerProcess(name, command, args, env)
            try:
                await server.start()
                self.servers[name] = server

                tools = await server.list_tools()
                for t in tools:
                    t_name = t.get("name")
                    t_desc = t.get("description", "")
                    t_schema = t.get("inputSchema", {})

                    wrapper = MCPToolWrapper(name, server, t_name, t_desc, t_schema)
                    register_tool(wrapper)
                    logger.info(f"Dynamically mapped and registered MCP tool: {t_name} from Server [{name}]")
            except Exception as e:
                logger.error(f"Failed to start and register MCP Server [{name}]: {e}")

    async def read_builtin_resource(self, uri: str, conversation_id: str | None = None) -> str:
        """Direct exposure API for host/LLM to fetch System read-only MCP resources (like Repo Map) asynchronously."""
        return await self.builtin_server.read_resource(uri, conversation_id)

    def read_builtin_resource_sync(self, uri: str, conversation_id: str | None = None) -> str:
        """Direct exposure API for host/LLM to fetch System read-only MCP resources (like Repo Map) synchronously."""
        return self.builtin_server.read_resource_sync(uri, conversation_id)

    async def stop_all_servers(self):
        """Gracefully stop all process-based servers."""
        for name, server in list(self.servers.items()):
            try:
                await server.stop()
            except Exception as e:
                logger.error(f"Error stopping server [{name}]: {e}")
        self.servers.clear()
        for tenant_id, servers in list(self._tenant_servers.items()):
            for name, server in list(servers.items()):
                try:
                    await server.stop()
                except Exception as e:
                    logger.error("Error stopping tenant MCP server %s: %s", name, e)
                unregister_tenant_tools(
                    tenant_id,
                    self._server_tools.pop((tenant_id, name), set()),
                )
        self._tenant_servers.clear()
        self._loaded_tenants.clear()

# Global Singleton Manager
mcp_bridge_manager = MCPBridgeManager()
