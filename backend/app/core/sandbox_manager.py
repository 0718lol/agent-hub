import asyncio
import logging
import os
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

logger = logging.getLogger("sandbox_manager")

# Unified max cap for characters of stdout/stderr read-backs
MAX_OUTPUT_LIMIT = 5000


class BaseSandbox(ABC):
    """Abstract interface class representing any code execution sandbox."""

    @abstractmethod
    async def execute(self, code: str, language: str, timeout: int, stdin_data: str = "") -> Dict[str, Any]:
        """Execute the given script code and return the standardized result dictionary."""
        pass


class SubprocessSandbox(BaseSandbox):
    """Legacy Subprocess-based local execution sandbox. Serves as a highly reliable fallback rail."""

    async def execute(self, code: str, language: str, timeout: int, stdin_data: str = "") -> Dict[str, Any]:
        logger.info(f"[Sandbox] Fallback Subprocess Sandbox executing [{language}] (timeout: {timeout}s)...")
        
        lang_config = {
            "python": {"ext": ".py", "cmd": ["python", "-u"]},
            "py": {"ext": ".py", "cmd": ["python", "-u"]},
            "javascript": {"ext": ".js", "cmd": ["node"]},
            "js": {"ext": ".js", "cmd": ["node"]},
            "typescript": {"ext": ".ts", "cmd": ["npx", "tsx"]},
            "ts": {"ext": ".ts", "cmd": ["npx", "tsx"]},
            "shell": {"ext": ".sh", "cmd": ["bash"]},
            "bash": {"ext": ".sh", "cmd": ["bash"]},
            "sh": {"ext": ".sh", "cmd": ["bash"]},
        }

        lang_key = language.lower().strip()
        if lang_key not in lang_config:
            return {
                "language": language,
                "status": "error",
                "stdout": "",
                "stderr": f"不支持的语言: {language}。支持: python, javascript, shell",
                "exit_code": -1,
                "duration_ms": 0,
                "truncated": False
            }

        config = lang_config[lang_key]
        tmp_dir = tempfile.mkdtemp(prefix="sandbox_")
        tmp_file = os.path.join(tmp_dir, f"code{config['ext']}")

        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(code)

            cmd = config["cmd"] + [tmp_file]
            start_time = time.perf_counter()

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if stdin_data else None,
                cwd=tmp_dir,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

            try:
                stdin_bytes = stdin_data.encode("utf-8") if stdin_data else None
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(input=stdin_bytes),
                    timeout=timeout,
                )
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)

                stdout = stdout_bytes.decode("utf-8", errors="replace")
                stderr = stderr_bytes.decode("utf-8", errors="replace")

                truncated = False
                if len(stdout) > MAX_OUTPUT_LIMIT:
                    stdout = stdout[:MAX_OUTPUT_LIMIT] + "\n... [输出截断]"
                    truncated = True
                if len(stderr) > MAX_OUTPUT_LIMIT:
                    stderr = stderr[:MAX_OUTPUT_LIMIT] + "\n... [输出截断]"
                    truncated = True

                status = "success" if proc.returncode == 0 else "error"

                return {
                    "language": language,
                    "status": status,
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": proc.returncode or 0,
                    "duration_ms": elapsed_ms,
                    "truncated": truncated,
                }

            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                return {
                    "language": language,
                    "status": "timeout",
                    "stdout": "",
                    "stderr": f"执行超时（限制 {timeout}s）",
                    "exit_code": -1,
                    "duration_ms": elapsed_ms,
                    "truncated": False,
                }

        except Exception as e:
            return {
                "language": language,
                "status": "error",
                "stdout": "",
                "stderr": f"本地沙盒启动失败: {str(e)}",
                "exit_code": -1,
                "duration_ms": 0,
                "truncated": False,
            }

        finally:
            try:
                os.unlink(tmp_file)
                os.rmdir(tmp_dir)
            except OSError:
                pass


class DockerSandbox(BaseSandbox):
    """Local Container-based absolute isolated execution sandbox using native Docker CLI subprocess."""

    def __init__(self):
        self.image_map = {
            "python": "python:3.12-slim",
            "py": "python:3.12-slim",
            "javascript": "node:20-slim",
            "js": "node:20-slim",
            "typescript": "node:20-slim",
            "ts": "node:20-slim",
        }

    async def check_availability(self) -> bool:
        """Verify if local Docker engine is alive and active."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)
            return proc.returncode == 0
        except Exception:
            return False

    async def execute(self, code: str, language: str, timeout: int, stdin_data: str = "") -> Dict[str, Any]:
        lang_key = language.lower().strip()
        img = self.image_map.get(lang_key)
        
        # Bash or shell uses local bash inside standard alpine/ubuntu or similar
        if not img:
            if lang_key in ("shell", "bash", "sh"):
                img = "alpine:latest"  # alpine contains basic sh/ash shell
            else:
                raise ValueError(f"Docker sandbox unsupported language: {language}")

        # Standard command injection inside container via stdin pipe
        cmd_runner = []
        if "python" in img:
            cmd_runner = ["python", "-u", "-"]
        elif "node" in img:
            # Node supports direct stdin pipe execution via -e
            cmd_runner = ["node", "-"]
        else: # Shell alpine
            cmd_runner = ["sh"]

        logger.info(f"[Sandbox] Spawning secure Docker Container sandbox [{img}] (timeout: {timeout}s)...")
        start_time = time.perf_counter()

        # Build secure container execution command:
        # --rm: automatically cleanup container
        # --network none: cut off all outgoing/incoming internet connections (Zero Trust)
        # --memory 128m: Memory limit cap (protect host from memory exhaustion)
        # --cpus 0.5: CPU allocation limit (protect host from CPU starvation)
        # -i: keep stdin open for code injection
        docker_cmd = [
            "docker", "run", "-i", "--rm",
            "--network", "none",
            "--memory", "128m",
            "--cpus", "0.5",
            img
        ] + cmd_runner

        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
            )

            # Injected script source code into container stdin pipe
            input_bytes = code.encode("utf-8")
            if stdin_data:
                # Append standard stdin inputs if provided
                input_bytes += b"\n" + stdin_data.encode("utf-8")

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(input=input_bytes),
                    timeout=timeout,
                )
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)

                stdout = stdout_bytes.decode("utf-8", errors="replace")
                stderr = stderr_bytes.decode("utf-8", errors="replace")

                truncated = False
                if len(stdout) > MAX_OUTPUT_LIMIT:
                    stdout = stdout[:MAX_OUTPUT_LIMIT] + "\n... [输出截断]"
                    truncated = True
                if len(stderr) > MAX_OUTPUT_LIMIT:
                    stderr = stderr[:MAX_OUTPUT_LIMIT] + "\n... [输出截断]"
                    truncated = True

                status = "success" if proc.returncode == 0 else "error"
                return {
                    "language": language,
                    "status": status,
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": proc.returncode or 0,
                    "duration_ms": elapsed_ms,
                    "truncated": truncated,
                }

            except asyncio.TimeoutError:
                # If timed out, forcefully kill the subprocess spawning docker
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                return {
                    "language": language,
                    "status": "timeout",
                    "stdout": "",
                    "stderr": f"Docker沙盒执行超时（限制 {timeout}s）",
                    "exit_code": -1,
                    "duration_ms": elapsed_ms,
                    "truncated": False,
                }

        except Exception as e:
            logger.error(f"Docker execution failed, falling back: {e}")
            raise e


class E2BSandbox(BaseSandbox):
    """Cloud-based AWS Firecracker MicroVM execution sandbox. Standard E2B API integration."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        # E2B Sandbox standard HTTP endpoints
        self.base_url = "https://api.e2b.dev"

    async def execute(self, code: str, language: str, timeout: int, stdin_data: str = "") -> Dict[str, Any]:
        """Spawns an AWS Firecracker microVM instance, executes the code and returns outputs."""
        logger.info(f"[Sandbox] Contacting E2B MicroVM Sandbox Cloud service (timeout: {timeout}s)...")
        start_time = time.perf_counter()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # 1. Create a lightweight sandboxed microVM instance
        # Using E2B's standard base template "base" or customized "code-interpreter"
        template_id = "base"
        
        # We use standard HTTP client to completely bypass heavy third-party SDK dependencies
        async with httpx_client_context() as client:
            try:
                # Spin up microVM
                spawn_resp = await client.post(
                    f"{self.base_url}/instances",
                    json={"templateID": template_id},
                    headers=headers,
                    timeout=15.0
                )
                if spawn_resp.status_code != 201:
                    raise RuntimeError(f"E2B microVM spawn failed: {spawn_resp.status_code} {spawn_resp.text}")

                instance = spawn_resp.json()
                instance_id = instance.get("instanceID")
                
                # 2. Write and execute code inside the microVM
                # Write standard file script
                ext_map = {"python": ".py", "py": ".py", "javascript": ".js", "js": ".js", "shell": ".sh", "bash": ".sh"}
                ext = ext_map.get(language.lower().strip(), ".py")
                target_file = f"/home/user/script{ext}"
                
                # Prepare execution run commands
                if language.lower().strip() in ("python", "py"):
                    run_cmd = f"python3 {target_file}"
                elif language.lower().strip() in ("javascript", "js"):
                    run_cmd = f"node {target_file}"
                else:
                    run_cmd = f"bash {target_file}"

                # Write script content
                write_payload = {
                    "cmd": f"cat << 'EOF' > {target_file}\n{code}\nEOF\n"
                }
                
                # Command execution endpoint
                exec_url = f"{self.base_url}/instances/{instance_id}/commands"
                await client.post(exec_url, json=write_payload, headers=headers, timeout=10.0)

                # Execute script run command
                exec_payload = {
                    "cmd": run_cmd,
                    "timeout": timeout
                }
                
                run_resp = await client.post(exec_url, json=exec_payload, headers=headers, timeout=float(timeout + 5))
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                
                # 3. Terminate microVM to clean up cloud resources
                try:
                    await client.delete(f"{self.base_url}/instances/{instance_id}", headers=headers, timeout=5.0)
                except Exception:
                    pass

                if run_resp.status_code != 200:
                    return {
                        "language": language,
                        "status": "error",
                        "stdout": "",
                        "stderr": f"E2B execution command error: {run_resp.text}",
                        "exit_code": -1,
                        "duration_ms": elapsed_ms,
                        "truncated": False
                    }

                run_data = run_resp.json()
                stdout = run_data.get("stdout", "")
                stderr = run_data.get("stderr", "")
                exit_code = run_data.get("exitCode", 0)

                truncated = False
                if len(stdout) > MAX_OUTPUT_LIMIT:
                    stdout = stdout[:MAX_OUTPUT_LIMIT] + "\n... [输出截断]"
                    truncated = True
                if len(stderr) > MAX_OUTPUT_LIMIT:
                    stderr = stderr[:MAX_OUTPUT_LIMIT] + "\n... [输出截断]"
                    truncated = True

                status = "success" if exit_code == 0 else "error"
                return {
                    "language": language,
                    "status": status,
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code,
                    "duration_ms": elapsed_ms,
                    "truncated": truncated
                }

            except Exception as e:
                logger.error(f"E2B execution crashed: {e}")
                raise e


class SandboxManager:
    """Orchestrates resilient sandboxing execution rails dynamically with auto-recovery fallbacks."""

    def __init__(self):
        self.subprocess_sandbox = SubprocessSandbox()
        self.docker_sandbox = DockerSandbox()
        self.e2b_api_key = os.environ.get("E2B_API_KEY", "")
        # Configuration control: allow explicitly forcing/disabling rails
        self.enable_docker = os.environ.get("AGENTHUB_DOCKER_SANDBOX", "true").lower() == "true"

    async def execute(self, code: str, language: str = "python", timeout: int = 10, stdin_data: str = "") -> Dict[str, Any]:
        """Main dispatcher entrypoint selecting the safest available Sandbox rail."""
        # --- Rail 1: Cloud E2B (Highest Priority when API Key configured) ---
        if self.e2b_api_key.strip():
            try:
                e2b_box = E2BSandbox(self.e2b_api_key)
                return await e2b_box.execute(code, language, timeout, stdin_data)
            except Exception as e:
                logger.warning(f"E2B Cloud Sandbox failed, fallback to next rail: {e}")

        # --- Rail 2: Local Docker Container Isolation ---
        if self.enable_docker:
            # Dynamic live check if Docker is up and running
            docker_available = await self.docker_sandbox.check_availability()
            if docker_available:
                try:
                    return await self.docker_sandbox.execute(code, language, timeout, stdin_data)
                except Exception as e:
                    logger.warning(f"Local Docker Sandbox failed, falling back to subprocess: {e}")

        # --- Rail 3: Local Subprocess Sandbox (Resilient Fallback) ---
        return await self.subprocess_sandbox.execute(code, language, timeout, stdin_data)


# Helper async context to handle httpx client cleanly
def httpx_client_context():
    import httpx
    return httpx.AsyncClient()


# Global Singleton Manager instance
sandbox_manager = SandboxManager()
