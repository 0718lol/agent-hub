import asyncio
import json
import logging
import os
import sys
from typing import Dict, Any, List, Optional
from app.tools.registry import AgentTool, ToolResult, register_tool

logger = logging.getLogger("mcp_bridge")

class MCPServerProcess:
    """Manages the life-cycle and communication of a single Stdio-based MCP Server process."""

    def __init__(self, name: str, command: str, args: List[str], env: Dict[str, str] = None):
        self.name = name
        self.command = command
        self.args = args
        self.env = {**os.environ, **(env or {})}
        self.process: asyncio.subprocess.Process = None
        self.rpc_id = 1
        self.pending_requests: Dict[int, asyncio.Future] = {}
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
        if not self._running:
            return
        self._running = False
        logger.info(f"Stopping MCP Server process [{self.name}]...")
        
        if self.listen_task:
            self.listen_task.cancel()
        if self.error_task:
            self.error_task.cancel()

        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning(f"MCP Server [{self.name}] did not terminate gracefully. Killing it...")
                try:
                    self.process.kill()
                except Exception:
                    pass
            except Exception as e:
                logger.debug(f"Exception during terminating MCP Server process [{self.name}]: {e}")
        
        for fut in self.pending_requests.values():
            if not fut.done():
                fut.set_exception(RuntimeError("MCP Server connection terminated."))
        self.pending_requests.clear()
        logger.info(f"MCP Server process [{self.name}] stopped.")

    async def list_tools(self) -> List[Dict[str, Any]]:
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

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
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

    async def list_tools(self) -> List[Dict[str, Any]]:
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

    async def list_resources(self) -> List[Dict[str, Any]]:
        """Expose Project Codebase Skeleton (Repo Map) as read-only standard MCP Resource."""
        return [
            {
                "uri": "workspace://repomap",
                "name": "Project Codebase Outline Map",
                "description": "AST-based compact structural outline maps of all classes, methods and signatures inside the workspace sandbox.",
                "mimeType": "text/markdown"
            }
        ]

    def read_resource_sync(self, uri: str, conversation_id: Optional[str] = None) -> str:
        """Standard synchronous implementation to read the content of the specified workspace resource URI."""
        if uri == "workspace://repomap":
            from app.core.repo_map import codebase_map_scanner
            # Pick workspace sandbox directory safely
            workspace_dir = r"D:\project\high agent-hub\backend"
            if conversation_id:
                sandbox_dir = os.path.join(r"D:\project\high agent-hub", "agenthub_export", conversation_id)
                if os.path.exists(sandbox_dir):
                    workspace_dir = sandbox_dir
                    
            logger.info(f"MCP Resource workspace://repomap called (Sync). Scanning workspace path: {workspace_dir}")
            return codebase_map_scanner.scan_directory(workspace_dir)
            
        raise ValueError(f"Unknown Resource URI: {uri}")

    async def read_resource(self, uri: str, conversation_id: Optional[str] = None) -> str:
        """Standard asynchronous wrapper to read resource."""
        return self.read_resource_sync(uri, conversation_id)

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
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
        self.servers: Dict[str, MCPServerProcess] = {}
        self.builtin_server = BuiltinMCPServer()

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
            with open(config_path, "r", encoding="utf-8") as f:
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

    async def read_builtin_resource(self, uri: str, conversation_id: Optional[str] = None) -> str:
        """Direct exposure API for host/LLM to fetch System read-only MCP resources (like Repo Map) asynchronously."""
        return await self.builtin_server.read_resource(uri, conversation_id)

    def read_builtin_resource_sync(self, uri: str, conversation_id: Optional[str] = None) -> str:
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

# Global Singleton Manager
mcp_bridge_manager = MCPBridgeManager()
