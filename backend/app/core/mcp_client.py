import asyncio
import json
import os
import sys

MCP_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "mcp_config.json")

class MCPClient:
    """Standard Model Context Protocol stdio client with async JSON-RPC 2.0 communication."""

    def __init__(self, name: str, command: str, args: list[str] = None, env: dict = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.process = None
        self.read_task = None
        self.stderr_task = None
        self._request_futures = {}
        self._next_id = 1
        self.is_connected = False
        self.tools = []

    async def start(self):
        full_env = os.environ.copy()
        full_env.update(self.env)
        try:
            self.process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=full_env,
                creationflags=0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW on Windows
            )
            self.is_connected = True
            self.read_task = asyncio.create_task(self._read_loop())
            self.stderr_task = asyncio.create_task(self._stderr_loop())
            # Initial connection discovery
            await self.list_tools()
        except Exception as e:
            self.is_connected = False
            print(f"[MCP Client {self.name}] Failed to start subprocess: {e}")

    async def _read_loop(self):
        try:
            while self.process and not self.process.stdout.at_eof():
                line = await self.process.stdout.readline()
                if not line:
                    break
                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue
                try:
                    msg = json.loads(line_str)
                    if "id" in msg:
                        future_id = msg["id"]
                        if future_id in self._request_futures:
                            fut = self._request_futures.pop(future_id)
                            if not fut.done():
                                fut.set_result(msg)
                except Exception as e:
                    print(f"[MCP Client {self.name}] Error parsing JSON-RPC: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[MCP Client {self.name}] Read loop exception: {e}")
        finally:
            self.is_connected = False

    async def _stderr_loop(self):
        try:
            while self.process and not self.process.stderr.at_eof():
                line = await self.process.stderr.readline()
                if not line:
                    break
                print(f"[MCP Server Log: {self.name}] {line.decode('utf-8', errors='replace').strip()}")
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def send_request(self, method: str, params: dict = None) -> dict:
        if not self.is_connected or not self.process:
            return {"error": {"message": "MCP Server not running"}}

        req_id = self._next_id
        self._next_id += 1

        req = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": req_id
        }

        fut = asyncio.get_running_loop().create_future()
        self._request_futures[req_id] = fut

        try:
            req_bytes = (json.dumps(req) + "\n").encode("utf-8")
            self.process.stdin.write(req_bytes)
            await self.process.stdin.drain()

            # Wait for response with 15 second timeout
            response = await asyncio.wait_for(fut, timeout=15.0)
            return response
        except asyncio.TimeoutError:
            if req_id in self._request_futures:
                self._request_futures.pop(req_id)
            return {"error": {"message": f"Request {method} timed out after 15 seconds"}}
        except Exception as e:
            if req_id in self._request_futures:
                self._request_futures.pop(req_id)
            return {"error": {"message": f"Connection exception: {e}"}}

    async def list_tools(self) -> list:
        resp = await self.send_request("tools/list")
        if "error" in resp:
            print(f"[MCP Client {self.name}] Failed to list tools: {resp['error']}")
            return []

        self.tools = resp.get("result", {}).get("tools", [])
        return self.tools

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        resp = await self.send_request("tools/call", {"name": tool_name, "arguments": arguments})
        if "error" in resp:
            return {"isError": True, "content": [{"type": "text", "text": resp["error"].get("message", "Error calling tool")}]}
        return resp.get("result", {})

    async def stop(self):
        self.is_connected = False
        if self.read_task:
            self.read_task.cancel()
        if self.stderr_task:
            self.stderr_task.cancel()
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except Exception:
                pass
            self.process = None
        for fut in self._request_futures.values():
            if not fut.done():
                fut.cancel()
        self._request_futures.clear()


class SystemMCPServer:
    """Built-in core in-memory MCP Server to support safe filesystem & shell commands within sandboxed workspaces."""

    def __init__(self):
        self.name = "SystemServer"
        self.is_connected = True
        self.tools = [
            {
                "name": "workspace_list_dir",
                "description": "列出当前物理沙盒工作空间内的所有文件和目录结构",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "相对沙盒根目录的路径（可选，默认为根目录）"}
                    }
                }
            },
            {
                "name": "workspace_read_file",
                "description": "读取沙盒内指定文件的文本内容",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "相对沙盒根目录的路径（必填）"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "workspace_write_file",
                "description": "物理写入文件内容至沙盒的指定路径，会自动创建父目录",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "相对沙盒根目录的路径（必填）"},
                        "content": {"type": "string", "description": "要写入的文本内容（必填）"}
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "workspace_run_command",
                "description": "在物理沙盒根目录下安全运行指定的 Shell 命令行，并捕获终端输出",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "要执行的命令行指令（如 'npm run build' 或 'python test.py' 等，必填）"}
                    },
                    "required": ["command"]
                }
            }
        ]

    async def list_tools(self) -> list:
        return self.tools

    def _is_safe_path(self, sandbox_dir: str, target_path: str) -> bool:
        """安全物理路径校验：确保目标路径经过真实符号链接解析后仍严格位于沙盒目录内部。"""
        try:
            abs_sandbox = os.path.realpath(sandbox_dir)
            abs_target = os.path.realpath(target_path)
            common = os.path.commonpath([abs_sandbox, abs_target])
            return common == abs_sandbox
        except Exception:
            return False

    async def call_tool(self, tool_name: str, arguments: dict, conversation_id: str = None) -> dict:
        if not conversation_id:
            return {"isError": True, "content": [{"type": "text", "text": "Error: conversation_id is required to resolve sandboxed paths"}]}

        workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        sandbox_dir = os.path.join(workspace_dir, "agenthub_export", conversation_id)
        os.makedirs(sandbox_dir, exist_ok=True)

        try:
            if tool_name == "workspace_list_dir":
                sub_path = arguments.get("path", "")
                target_dir = os.path.abspath(os.path.join(sandbox_dir, sub_path))
                if not self._is_safe_path(sandbox_dir, target_dir):
                    return {"isError": True, "content": [{"type": "text", "text": "Error: Path traversal protection triggered"}]}

                if not os.path.exists(target_dir):
                    return {"isError": True, "content": [{"type": "text", "text": f"Error: Directory '{sub_path}' does not exist"}]}

                items = []
                for entry in os.scandir(target_dir):
                    items.append({
                        "name": entry.name,
                        "is_dir": entry.is_dir(),
                        "size": entry.stat().st_size if entry.is_file() else 0
                    })
                return {"content": [{"type": "text", "text": json.dumps(items, ensure_ascii=False, indent=2)}]}

            elif tool_name == "workspace_read_file":
                sub_path = arguments.get("path", "")
                target_file = os.path.abspath(os.path.join(sandbox_dir, sub_path))
                if not self._is_safe_path(sandbox_dir, target_file):
                    return {"isError": True, "content": [{"type": "text", "text": "Error: Path traversal protection triggered"}]}

                if not os.path.exists(target_file) or not os.path.isfile(target_file):
                    return {"isError": True, "content": [{"type": "text", "text": f"Error: File '{sub_path}' not found"}]}

                with open(target_file, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                return {"content": [{"type": "text", "text": content}]}

            elif tool_name == "workspace_write_file":
                sub_path = arguments.get("path", "")
                content = arguments.get("content", "")
                target_file = os.path.abspath(os.path.join(sandbox_dir, sub_path))
                if not self._is_safe_path(sandbox_dir, target_file):
                    return {"isError": True, "content": [{"type": "text", "text": "Error: Path traversal protection triggered"}]}


                # 1. Create pre-write checkpoint
                from app.core.git_sandbox import git_checkpoint, git_rollback
                await git_checkpoint(sandbox_dir, f"Pre-write: {sub_path}")

                # 2. Write the file physically
                os.makedirs(os.path.dirname(target_file), exist_ok=True)
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write(content)

                # 3. Perform implicit Quality Gate / compile checks on written file
                is_valid = True
                error_msg = ""
                if target_file.endswith(".py"):
                    try:
                        import py_compile
                        py_compile.compile(target_file, doraise=True)
                    except Exception as e:
                        is_valid = False
                        error_msg = f"Python Syntax Error: {e}"

                if not is_valid:
                    # Trigger auto-healing rollback
                    await git_rollback(sandbox_dir)
                    return {"isError": True, "content": [{"type": "text", "text": f"❌ 写入失败！检测到代码语法缺陷，沙盒工作空间已安全自愈回滚。\n详情: {error_msg}"}]}

                # Create success checkpoint
                await git_checkpoint(sandbox_dir, f"Success-write: {sub_path}")
                return {"content": [{"type": "text", "text": f"Success: File successfully written to sandbox: {sub_path}"}]}

            elif tool_name == "workspace_run_command":
                cmd = arguments.get("command", "")
                
                # 1. Create pre-command checkpoint
                from app.core.git_sandbox import git_checkpoint, git_rollback
                await git_checkpoint(sandbox_dir, f"Pre-command: {cmd}")

                # 2. Execute command
                enable_docker = os.environ.get("AGENTHUB_DOCKER_SANDBOX", "true").lower() == "true"
                docker_available = False
                if enable_docker:
                    try:
                        proc_check = await asyncio.create_subprocess_exec(
                            "docker", "info",
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            creationflags=0x08000000 if sys.platform == "win32" else 0
                        )
                        await asyncio.wait_for(proc_check.communicate(), timeout=2.0)
                        docker_available = (proc_check.returncode == 0)
                    except Exception:
                        docker_available = False

                script_path = None
                try:
                    if enable_docker and docker_available:
                        # Select suitable image
                        image = "node:20-slim"
                        if "python" in cmd or ".py" in cmd:
                            image = "python:3.12-slim"
                        elif "npm" in cmd or "node" in cmd or "vite" in cmd:
                            image = "node:20-slim"

                        docker_cmd = [
                            "docker", "run", "--rm",
                            "--network", "none",
                            "--memory", "128m",
                            "--cpus", "0.5",
                            "-v", f"{os.path.abspath(sandbox_dir)}:/workspace",
                            "-w", "/workspace",
                            image,
                            "sh", "-c", cmd
                        ]
                        
                        proc = await asyncio.create_subprocess_exec(
                            *docker_cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            creationflags=0x08000000 if sys.platform == "win32" else 0
                        )
                    else:
                        # Non-Docker fallback verification and wrapping
                        from app.core.config import settings
                        if not settings.allow_unsandboxed_shell:
                            return {"isError": True, "content": [{"type": "text", "text": "❌ 安全限制：未启用或未检测到 Docker 环境，且本地非沙盒命令执行开关已禁用。若需在本地宿主机执行，请设置环境变量 AGENTHUB_ALLOW_UNSANDBOXED_SHELL=true"}]}

                        import uuid
                        script_name = f"temp_run_{uuid.uuid4().hex}"
                        if sys.platform == "win32":
                            script_path = os.path.join(sandbox_dir, f"{script_name}.bat")
                            with open(script_path, "w", encoding="utf-8") as f:
                                f.write(f"@echo off\r\ncd /d %~dp0\r\n{cmd}\r\n")
                            exec_cmd = ["cmd.exe", "/c", script_path]
                        else:
                            script_path = os.path.join(sandbox_dir, f"{script_name}.sh")
                            with open(script_path, "w", encoding="utf-8") as f:
                                f.write(f"#!/bin/bash\ncd \"$(dirname \"$0\")\"\n{cmd}\n")
                            try:
                                os.chmod(script_path, 0o755)
                            except Exception:
                                pass
                            exec_cmd = ["/bin/bash", script_path]

                        proc = await asyncio.create_subprocess_exec(
                            *exec_cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            cwd=sandbox_dir,
                            creationflags=0x08000000 if sys.platform == "win32" else 0
                        )
                    
                    stdout, stderr = await proc.communicate()
                finally:
                    # Physically clean up the wrapped script file so it doesn't pollute the git sandbox
                    if script_path and os.path.exists(script_path):
                        try:
                            os.remove(script_path)
                        except Exception:
                            pass

                out_str = stdout.decode("utf-8", errors="replace")
                err_str = stderr.decode("utf-8", errors="replace")

                result = f"Command exited with code: {proc.returncode}\n"
                if out_str:
                    result += f"--- STDOUT ---\n{out_str}\n"
                if err_str:
                    result += f"--- STDERR ---\n{err_str}\n"

                # 3. Quality Gate check: Rollback on command failure (non-zero code)
                if proc.returncode != 0:
                    # Trigger auto-healing rollback
                    await git_rollback(sandbox_dir)
                    return {"isError": True, "content": [{"type": "text", "text": f"❌ 指令执行失败！沙盒工作空间已安全自动回滚至修改前状态以防止文件损坏。\n{result}"}]}

                # Create success checkpoint
                await git_checkpoint(sandbox_dir, f"Success-command: {cmd}")
                return {"content": [{"type": "text", "text": result}]}

            else:
                return {"isError": True, "content": [{"type": "text", "text": f"Error: Unknown system tool name '{tool_name}'"}]}
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": f"Error: Exception during execution: {e}"}]}


class MCPManager:
    """Global manager to handle discovery, starting/stopping and execution routing for all standard stdio servers."""

    def __init__(self):
        self.servers = {}
        self.config = {}
        self.servers["SystemServer"] = SystemMCPServer()

    def load_config(self):
        try:
            if os.path.exists(MCP_CONFIG_PATH):
                with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            else:
                self.config = {"servers": {}}
        except Exception:
            self.config = {"servers": {}}

    def save_config(self):
        os.makedirs(os.path.dirname(MCP_CONFIG_PATH), exist_ok=True)
        try:
            with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    async def start_all(self):
        self.load_config()
        ext_servers = self.config.get("servers", {})
        for sname, scfg in ext_servers.items():
            cmd = scfg.get("command")
            if not cmd:
                continue
            args = scfg.get("args", [])
            env = scfg.get("env", {})
            client = MCPClient(sname, cmd, args, env)
            self.servers[sname] = client
            asyncio.create_task(client.start())

    async def add_server(self, name: str, command: str, args: list[str] = None, env: dict = None):
        self.load_config()
        if "servers" not in self.config:
            self.config["servers"] = {}
        self.config["servers"][name] = {
            "command": command,
            "args": args or [],
            "env": env or {}
        }
        self.save_config()

        if name in self.servers and name != "SystemServer":
            await self.servers[name].stop()

        client = MCPClient(name, command, args or [], env or {})
        self.servers[name] = client
        await client.start()

    async def remove_server(self, name: str):
        self.load_config()
        if name == "SystemServer":
            return
        if "servers" in self.config and name in self.config["servers"]:
            self.config["servers"].pop(name)
            self.save_config()
        if name in self.servers:
            client = self.servers.pop(name)
            await client.stop()

    async def get_all_tools(self) -> list:
        all_tools = []
        for sname, srv in self.servers.items():
            try:
                tools = await srv.list_tools()
                for t in tools:
                    all_tools.append({
                        "server_name": sname,
                        "name": f"{sname}__{t['name']}",
                        "description": t.get("description", ""),
                        "inputSchema": t.get("inputSchema", t.get("schema", {}))
                    })
            except Exception as e:
                print(f"[MCP Manager] Failed listing tools from {sname}: {e}")
        return all_tools

    async def execute_tool(self, namespaced_name: str, arguments: dict, conversation_id: str = None) -> dict:
        if "__" not in namespaced_name:
            return {"isError": True, "content": [{"type": "text", "text": f"Error: Invalid tool name format '{namespaced_name}'"}]}

        parts = namespaced_name.split("__", 1)
        sname = parts[0]
        tool_name = parts[1]

        if sname not in self.servers:
            return {"isError": True, "content": [{"type": "text", "text": f"Error: MCP Server '{sname}' is not running"}]}

        srv = self.servers[sname]
        try:
            if sname == "SystemServer":
                return await srv.call_tool(tool_name, arguments, conversation_id)
            else:
                return await srv.call_tool(tool_name, arguments)
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": f"Error: Exception calling tool: {e}"}]}

    async def stop_all(self):
        for sname, srv in list(self.servers.items()):
            if sname != "SystemServer":
                try:
                    await srv.stop()
                except Exception:
                    pass
        self.servers = {"SystemServer": self.servers["SystemServer"]}

mcp_manager = MCPManager()
