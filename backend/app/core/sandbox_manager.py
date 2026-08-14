import asyncio
import base64
import io
import json
import logging
import os
import re
import secrets
import shlex
import sys
import tarfile
import tempfile
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.sandbox_dependencies import (
    DependencyPlan,
    DependencyPolicyError,
    resolve_dependencies,
)

_logger = logging.getLogger("sandbox_manager")
from app.core.subprocess_security import limit_windows_process, safe_terminate_process_tree

logger = logging.getLogger("sandbox_manager")

# Unified max cap for characters of stdout/stderr read-backs
MAX_OUTPUT_LIMIT = 5000
CONTAINER_TMPFS_MOUNT = "/tmp:rw,nosuid,size=512m"  # nosec B108
COMMAND_FILE = ".agenthub-command"
COMMAND_PATH = "/tmp/workspace/.agenthub-command"  # nosec B108


class BaseSandbox(ABC):
    """Abstract interface class representing any code execution sandbox."""

    @abstractmethod
    async def execute(
        self,
        code: str,
        language: str,
        timeout: int,
        stdin_data: str = "",
        workspace: str | Path | None = None,
    ) -> dict[str, Any]:
        """Execute the given script code and return the standardized result dictionary."""
        pass


class SubprocessSandbox(BaseSandbox):
    """Legacy Subprocess-based local execution sandbox. Serves as a highly reliable fallback rail."""

    async def execute(
        self,
        code: str,
        language: str,
        timeout: int,
        stdin_data: str = "",
        workspace: str | Path | None = None,
    ) -> dict[str, Any]:
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

            # Enforce dynamic resource limitations: ulimit for Unix/Linux, Job Objects for Windows
            if sys.platform != "win32":
                # Unix/Linux path: encapsulate command in bash/sh with memory and CPU ulimits
                # CPU limit: timeout + 2 seconds buffer
                cpu_limit_secs = int(timeout) + 2
                memory_kb = settings.shell_memory_limit_mb * 1024
                # We use shlex.join to construct a perfectly shell-escaped execute command
                exec_str = f"ulimit -t {cpu_limit_secs} && ulimit -v {memory_kb} && exec {shlex.join(cmd)}"
                proc = await asyncio.create_subprocess_exec(
                    "sh", "-c", exec_str,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.PIPE if stdin_data else None,
                    cwd=tmp_dir,
                    env={
                        "PATH": os.environ.get("PATH", ""),
                        "LANG": "C.UTF-8",
                        "PYTHONDONTWRITEBYTECODE": "1",
                        "PYTHONIOENCODING": "utf-8",
                    },
                )
            else:
                # Windows path: execute directly, then attach Windows Job Object constraints immediately after creation
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.PIPE if stdin_data else None,
                    cwd=tmp_dir,
                    env={
                        "PATH": os.environ.get("PATH", ""),
                        "LANG": "C.UTF-8",
                        "PYTHONDONTWRITEBYTECODE": "1",
                        "PYTHONIOENCODING": "utf-8",
                    },
                )
                limit_windows_process(proc.pid, settings.shell_memory_limit_mb * 1024 * 1024, cpu_limit_secs=timeout + 2)

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

            except TimeoutError:
                await safe_terminate_process_tree(proc)
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
                "stderr": f"本地沙盒启动失败: {e!s}",
                "exit_code": -1,
                "duration_ms": 0,
                "truncated": False,
            }

        finally:
            for _ in range(5):
                try:
                    if os.path.exists(tmp_file):
                        os.unlink(tmp_file)
                    if os.path.exists(tmp_dir):
                        os.rmdir(tmp_dir)
                    break
                except OSError:
                    await asyncio.sleep(0.1)


class DockerSandbox(BaseSandbox):
    """Docker execution sandbox with remote-safe source transfer and dependency caches."""

    _IGNORED_WORKSPACE_PARTS = {
        ".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build",
    }

    def __init__(self):
        self.image_map = {
            language: settings.runtime_sandbox_image
            for language in (
                "python", "py", "javascript", "js", "typescript", "ts",
                "shell", "bash", "sh",
            )
        }
        self._probe_lock = asyncio.Lock()
        self._probe_time = 0.0
        self._probe_result = False
        self._dependency_locks: dict[str, asyncio.Lock] = {}
        self._ready_dependency_volumes: set[str] = set()
        self._active_dependency_volumes: set[str] = set()

    @staticmethod
    async def _run_cli(args: list[str], timeout: float = 30) -> tuple[int, bytes, bytes]:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode or 0, stdout, stderr
        except TimeoutError:
            await safe_terminate_process_tree(proc)
            raise

    @classmethod
    def _create_workspace_archive(
        cls,
        workspace: str | Path,
        command: str | None = None,
    ) -> Path:
        root = Path(workspace).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Sandbox workspace must be a directory")

        handle, archive_name = tempfile.mkstemp(prefix="agenthub-workspace-", suffix=".tar")
        os.close(handle)
        archive_path = Path(archive_name)
        file_count = 0
        total_bytes = 0
        try:
            with tarfile.open(archive_path, "w") as archive:
                for path in root.rglob("*"):
                    relative = path.relative_to(root)
                    if any(part in cls._IGNORED_WORKSPACE_PARTS for part in relative.parts):
                        continue
                    if relative.as_posix() == COMMAND_FILE:
                        continue
                    if path.is_symlink() or not path.is_file():
                        continue
                    stat = path.stat()
                    file_count += 1
                    total_bytes += stat.st_size
                    if file_count > settings.runtime_sandbox_archive_max_files:
                        raise ValueError("Sandbox workspace contains too many files")
                    if total_bytes > settings.runtime_sandbox_archive_max_bytes:
                        raise ValueError("Sandbox workspace is too large")
                    archive.add(path, arcname=relative.as_posix(), recursive=False)
                if command is not None:
                    command_bytes = command.encode("utf-8")
                    command_info = tarfile.TarInfo(COMMAND_FILE)
                    command_info.mode = 0o400
                    command_info.size = len(command_bytes)
                    archive.addfile(command_info, io.BytesIO(command_bytes))
            return archive_path
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise

    async def check_availability(self) -> bool:
        """Check Docker at a bounded frequency to avoid one probe per command."""
        now = time.monotonic()
        if now - self._probe_time < settings.runtime_sandbox_docker_probe_ttl:
            return self._probe_result
        async with self._probe_lock:
            now = time.monotonic()
            if now - self._probe_time < settings.runtime_sandbox_docker_probe_ttl:
                return self._probe_result
            try:
                returncode, _stdout, _stderr = await self._run_cli(["info"], timeout=2)
                self._probe_result = returncode == 0
            except Exception:
                self._probe_result = False
            self._probe_time = time.monotonic()
            return self._probe_result

    @staticmethod
    def _runner(language: str) -> list[str]:
        lang_key = language.lower().strip()
        if lang_key in ("python", "py"):
            return ["python", "-u", "-"]
        if lang_key in ("javascript", "js"):
            return ["node", "-"]
        if lang_key in ("typescript", "ts"):
            return ["tsx", "-"]
        if lang_key in ("shell", "bash", "sh"):
            return ["sh"]
        raise ValueError(f"Docker sandbox unsupported language: {language}")

    @staticmethod
    def _result(
        language: str,
        status: str,
        stdout: bytes | str,
        stderr: bytes | str,
        exit_code: int,
        started_at: float,
    ) -> dict[str, Any]:
        stdout_text = stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else stdout
        stderr_text = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else stderr
        truncated = False
        if len(stdout_text) > MAX_OUTPUT_LIMIT:
            stdout_text = stdout_text[:MAX_OUTPUT_LIMIT] + "\n... [输出截断]"
            truncated = True
        if len(stderr_text) > MAX_OUTPUT_LIMIT:
            stderr_text = stderr_text[:MAX_OUTPUT_LIMIT] + "\n... [输出截断]"
            truncated = True
        return {
            "language": language,
            "status": status,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "exit_code": exit_code,
            "duration_ms": int((time.perf_counter() - started_at) * 1000),
            "truncated": truncated,
        }

    async def _cleanup_container(self, container_name: str) -> None:
        try:
            await self._run_cli(["rm", "-f", container_name], timeout=10)
        except Exception as exc:
            _logger.warning("Failed to remove sandbox container %s: %s", container_name, exc)

    async def _execute_container(
        self,
        code: str,
        language: str,
        timeout: int,
        *,
        workspace: str | Path | None,
        network: str,
        mounts: tuple[str, ...] = (),
        environment: tuple[tuple[str, str], ...] = (),
        runtime_bootstrap: tuple[str, ...] = (),
        user: str = "65532:65532",
    ) -> dict[str, Any]:
        image = self.image_map.get(language.lower().strip())
        if not image:
            raise ValueError(f"Docker sandbox unsupported language: {language}")

        started_at = time.perf_counter()
        archive_path: Path | None = None
        container_name = f"agenthub-sandbox-{secrets.token_hex(8)}"
        created = False
        runner = self._runner(language)
        bootstrap_parts: list[str] = []
        command = code
        if workspace is not None:
            archive_path = await asyncio.to_thread(
                self._create_workspace_archive,
                workspace,
                command,
            )
            bootstrap_parts.extend([
                "mkdir -p /tmp/workspace",
                "tar --no-same-owner -xf - -C /tmp/workspace",
                *runtime_bootstrap,
                "cd /tmp/workspace",
            ])
            if runner[-1] == "-":
                runner[-1] = COMMAND_PATH
            else:
                runner.append(COMMAND_PATH)
        if bootstrap_parts:
            bootstrap_parts.append(f"exec {shlex.join(runner)}")
            runner = ["sh", "-lc", " && ".join(bootstrap_parts)]

        options = [
            "create", "-i", "--name", container_name,
            "--network", network,
            "--memory", settings.runtime_sandbox_memory,
            "--cpus", settings.runtime_sandbox_cpus,
            "--pids-limit", str(settings.runtime_sandbox_pids),
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--read-only",
            "--tmpfs", CONTAINER_TMPFS_MOUNT,
            "--user", user,
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-e", "HOME=/tmp",
        ]
        for key, value in environment:
            options.extend(["-e", f"{key}={value}"])
        for mount in mounts:
            options.extend(["--mount", mount])
        options.extend([image, *runner])

        try:
            returncode, _stdout, stderr = await self._run_cli(options)
            if returncode != 0:
                return self._result(language, "error", b"", stderr, returncode, started_at)
            created = True

            proc = await asyncio.create_subprocess_exec(
                "docker", "start", "-a", "-i", container_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
            )
            try:
                input_bytes = (
                    await asyncio.to_thread(archive_path.read_bytes)
                    if archive_path is not None
                    else command.encode("utf-8")
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=input_bytes),
                    timeout=timeout,
                )
            except TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception as exc:
                    _logger.warning("Failed to stop timed-out Docker client: %s", exc)
                return self._result(
                    language,
                    "timeout",
                    b"",
                    f"Docker沙盒执行超时（限制 {timeout}s）",
                    -1,
                    started_at,
                )
            except asyncio.CancelledError:
                await safe_terminate_process_tree(proc)
                raise
            status = "success" if proc.returncode == 0 else "error"
            return self._result(language, status, stdout, stderr, proc.returncode or 0, started_at)
        finally:
            if created:
                await self._cleanup_container(container_name)
            if archive_path is not None:
                archive_path.unlink(missing_ok=True)

    async def _volume_exists(self, volume_name: str) -> bool:
        try:
            returncode, _stdout, _stderr = await self._run_cli(["volume", "inspect", volume_name])
            return returncode == 0
        except Exception:
            return False

    async def _dependency_ready(self, plan: DependencyPlan) -> bool:
        if plan.volume_name in self._ready_dependency_volumes:
            return True
        if not await self._volume_exists(plan.volume_name):
            return False
        image = self.image_map["shell"]
        returncode, _stdout, _stderr = await self._run_cli([
            "run", "--rm", "--network", "none",
            "--mount", plan.mount(readonly=True),
            image,
            "test", "-f", f"{plan.target}/.agenthub-ready",
        ])
        if returncode == 0:
            self._ready_dependency_volumes.add(plan.volume_name)
            return True
        await self._run_cli(["volume", "rm", "-f", plan.volume_name])
        return False

    async def _prune_dependency_volumes(self, protected: set[str]) -> None:
        maximum = max(1, settings.runtime_sandbox_dependency_cache_max)
        try:
            returncode, stdout, _stderr = await self._run_cli([
                "volume", "ls",
                "--filter", "label=agenthub.kind=sandbox-dependency",
                "--format", "{{.Name}}",
            ])
            if returncode != 0:
                return
            names = [line.strip() for line in stdout.decode().splitlines() if line.strip()]
            if len(names) <= maximum:
                return
            returncode, stdout, _stderr = await self._run_cli(["volume", "inspect", *names])
            if returncode != 0:
                return
            metadata = json.loads(stdout.decode("utf-8"))
            ordered = sorted(metadata, key=lambda item: str(item.get("CreatedAt", "")))
            excess = len(names) - maximum
            for item in ordered:
                name = str(item.get("Name", ""))
                if excess <= 0:
                    break
                if not name or name in protected or name in self._active_dependency_volumes:
                    continue
                returncode, _stdout, _stderr = await self._run_cli(["volume", "rm", name])
                if returncode == 0:
                    self._ready_dependency_volumes.discard(name)
                    excess -= 1
        except Exception as exc:
            _logger.debug("Dependency cache pruning failed: %s", exc)

    async def _ensure_dependency(
        self,
        plan: DependencyPlan,
        workspace: str | Path,
    ) -> dict[str, Any] | None:
        lock = self._dependency_locks.setdefault(plan.volume_name, asyncio.Lock())
        async with lock:
            if await self._dependency_ready(plan):
                return None
            network = settings.runtime_dependency_network.strip()
            if not network or network == "host" or network.startswith("container:"):
                return self._result(
                    plan.ecosystem,
                    "error",
                    "",
                    "Dependency network must be a bridge or a dedicated egress network.",
                    -1,
                    time.perf_counter(),
                )
            returncode, _stdout, stderr = await self._run_cli([
                "volume", "create",
                "--label", "agenthub.managed=true",
                "--label", "agenthub.kind=sandbox-dependency",
                plan.volume_name,
            ])
            if returncode != 0:
                return self._result(plan.ecosystem, "error", b"", stderr, returncode, time.perf_counter())

            result = await self._execute_container(
                plan.install_script,
                "shell",
                settings.runtime_sandbox_dependency_timeout,
                workspace=workspace,
                network=network,
                mounts=(plan.mount(readonly=False),),
                environment=plan.install_environment,
                user="0:0",
            )
            if result["status"] != "success":
                await self._run_cli(["volume", "rm", "-f", plan.volume_name])
                return result
            self._ready_dependency_volumes.add(plan.volume_name)
            await self._prune_dependency_volumes({plan.volume_name})
            return None

    async def execute(
        self,
        code: str,
        language: str,
        timeout: int,
        stdin_data: str = "",
        workspace: str | Path | None = None,
    ) -> dict[str, Any]:
        self._runner(language)
        plans: tuple[DependencyPlan, ...] = ()
        install_only = False
        if workspace is not None and language.lower().strip() in ("shell", "bash", "sh"):
            try:
                resolution = resolve_dependencies(Path(workspace), code)
            except DependencyPolicyError as exc:
                return self._result(language, "error", "", f"依赖策略拒绝: {exc}", -1, time.perf_counter())
            plans = resolution.plans
            install_only = resolution.install_only
            for plan in plans:
                failure = await self._ensure_dependency(plan, workspace)
                if failure is not None:
                    return failure

        if install_only:
            ecosystems = ", ".join(plan.ecosystem for plan in plans)
            return self._result(
                language,
                "success",
                f"依赖已准备并缓存: {ecosystems}\n",
                "",
                0,
                time.perf_counter(),
            )

        mounts = tuple(plan.mount(readonly=True) for plan in plans)
        environment = [item for plan in plans for item in plan.runtime_environment]
        if plans:
            path_parts = []
            if any(plan.ecosystem == "python" for plan in plans):
                path_parts.append("/deps/python/venv/bin")
            if any(plan.ecosystem == "node" for plan in plans):
                path_parts.append("/deps/node/node_modules/.bin")
            path_parts.append("/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
            environment.append(("PATH", ":".join(path_parts)))
        bootstrap = tuple(plan.runtime_bootstrap for plan in plans if plan.runtime_bootstrap)
        command = code + ("\n" + stdin_data if stdin_data else "")
        active_names = {plan.volume_name for plan in plans}
        self._active_dependency_volumes.update(active_names)
        try:
            return await self._execute_container(
                command,
                language,
                timeout,
                workspace=workspace,
                network="none",
                mounts=mounts,
                environment=tuple(environment),
                runtime_bootstrap=bootstrap,
            )
        finally:
            self._active_dependency_volumes.difference_update(active_names)


class E2BSandbox(BaseSandbox):
    """Cloud-based AWS Firecracker MicroVM execution sandbox. Standard E2B API integration."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        # E2B Sandbox standard HTTP endpoints
        self.base_url = "https://api.e2b.dev"

    async def execute(
        self,
        code: str,
        language: str,
        timeout: int,
        stdin_data: str = "",
        workspace: str | Path | None = None,
    ) -> dict[str, Any]:
        """Spawns an AWS Firecracker microVM instance, executes the code and returns outputs."""
        logger.info(f"[Sandbox] Contacting E2B MicroVM Sandbox Cloud service (timeout: {timeout}s)...")
        start_time = time.perf_counter()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # 1. Create a lightweight sandboxed microVM instance
        template_id = settings.e2b_template_id

        # We use standard HTTP client to completely bypass heavy third-party SDK dependencies
        async with httpx_client_context() as client:
            instance_id = ""
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
                instance_id = str(instance.get("instanceID") or "")
                if not re.fullmatch(r"[A-Za-z0-9_-]{6,128}", instance_id):
                    raise RuntimeError("E2B microVM returned an invalid instance ID")

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
                encoded_code = base64.b64encode(code.encode("utf-8")).decode("ascii")
                write_payload = {
                    "cmd": f"printf %s {shlex.quote(encoded_code)} | base64 -d > {target_file}"
                }

                # Command execution endpoint
                exec_url = f"{self.base_url}/instances/{instance_id}/commands"
                write_resp = await client.post(
                    exec_url,
                    json=write_payload,
                    headers=headers,
                    timeout=10.0,
                )
                if write_resp.status_code not in (200, 201, 202):
                    raise RuntimeError(f"E2B script upload failed: {write_resp.status_code}")

                if language.lower().strip() in ("python", "py"):
                    preflight_resp = await client.post(
                        exec_url,
                        json={
                            "cmd": "python3 -c 'import numpy, pandas, matplotlib'",
                            "timeout": 10,
                        },
                        headers=headers,
                        timeout=15.0,
                    )
                    if preflight_resp.status_code != 200:
                        raise RuntimeError("E2B data-science capability check failed")
                    preflight_data = preflight_resp.json()
                    if preflight_data.get("exitCode", -1) != 0:
                        raise RuntimeError(
                            "Configured E2B template does not provide numpy, pandas, and matplotlib"
                        )

                # Execute script run command
                exec_payload = {
                    "cmd": run_cmd,
                    "timeout": timeout
                }

                run_resp = await client.post(exec_url, json=exec_payload, headers=headers, timeout=float(timeout + 5))
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)

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
                raise
            finally:
                if instance_id:
                    try:
                        await client.delete(
                            f"{self.base_url}/instances/{instance_id}",
                            headers=headers,
                            timeout=5.0,
                        )
                    except Exception as e:
                        _logger.warning(f"Failed to delete E2B microVM instance: {e}")


class SandboxManager:
    """Orchestrates resilient sandboxing execution rails dynamically with auto-recovery fallbacks."""

    def __init__(self):
        self.subprocess_sandbox = SubprocessSandbox()
        self.docker_sandbox = DockerSandbox()
        self.e2b_api_key = os.environ.get("E2B_API_KEY", "")
        # Configuration control: allow explicitly forcing/disabling rails
        self.enable_docker = os.environ.get("AGENTHUB_DOCKER_SANDBOX", "true").lower() == "true"
        self._global_semaphore = asyncio.Semaphore(max(1, settings.runtime_sandbox_max_concurrency))
        self._tenant_semaphores: dict[str, asyncio.Semaphore] = {}

    @staticmethod
    def _tenant_key(quota_key: str | None) -> str:
        value = (quota_key or "anonymous").strip()
        if "__conv__" in value:
            value = value.split("__conv__", 1)[0]
        return value[:160] or "anonymous"

    async def _dispatch(
        self,
        code: str,
        language: str,
        timeout: int,
        stdin_data: str,
        workspace: str | Path | None,
    ) -> dict[str, Any]:
        """Select the safest available sandbox rail after quota admission."""
        if self.e2b_api_key.strip() and workspace is None:
            try:
                e2b_box = E2BSandbox(self.e2b_api_key)
                return await e2b_box.execute(code, language, timeout, stdin_data)
            except Exception as e:
                logger.warning(f"E2B Cloud Sandbox failed, fallback to next rail: {e}")

        if self.enable_docker:
            docker_available = await self.docker_sandbox.check_availability()
            if docker_available:
                try:
                    return await self.docker_sandbox.execute(
                        code,
                        language,
                        timeout,
                        stdin_data,
                        workspace,
                    )
                except Exception as e:
                    logger.warning(f"Local Docker Sandbox failed, falling back to subprocess: {e}")

        if settings.allow_unsandboxed_shell:
            if workspace is not None:
                return {
                    "language": language,
                    "status": "error",
                    "stdout": "",
                    "stderr": "Project commands require the Docker sandbox; host execution is disabled for generated workspaces.",
                    "exit_code": -1,
                    "duration_ms": 0,
                    "truncated": False,
                }
            logger.warning("Executing code in explicitly enabled host subprocess fallback")
            return await self.subprocess_sandbox.execute(code, language, timeout, stdin_data)

        return {
            "language": language,
            "status": "error",
            "stdout": "",
            "stderr": "No isolated sandbox is available. Start Docker, configure E2B, or explicitly enable AGENTHUB_ALLOW_UNSANDBOXED_SHELL for local development.",
            "exit_code": -1,
            "duration_ms": 0,
            "truncated": False,
        }

    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout: int = 10,
        stdin_data: str = "",
        workspace: str | Path | None = None,
        quota_key: str | None = None,
    ) -> dict[str, Any]:
        """Admit execution through global and per-tenant quotas, then dispatch it."""
        tenant_key = self._tenant_key(quota_key)
        tenant_semaphore = self._tenant_semaphores.setdefault(
            tenant_key,
            asyncio.Semaphore(max(1, settings.runtime_sandbox_max_per_tenant)),
        )
        global_acquired = False
        tenant_acquired = False
        deadline = time.monotonic() + settings.runtime_sandbox_queue_timeout
        try:
            await asyncio.wait_for(
                self._global_semaphore.acquire(),
                timeout=max(0.001, deadline - time.monotonic()),
            )
            global_acquired = True
            await asyncio.wait_for(
                tenant_semaphore.acquire(),
                timeout=max(0.001, deadline - time.monotonic()),
            )
            tenant_acquired = True
            return await self._dispatch(code, language, timeout, stdin_data, workspace)
        except TimeoutError:
            return {
                "language": language,
                "status": "error",
                "stdout": "",
                "stderr": "Sandbox queue is busy. Retry after an active execution finishes.",
                "exit_code": -1,
                "duration_ms": 0,
                "truncated": False,
            }
        finally:
            if tenant_acquired:
                tenant_semaphore.release()
            if global_acquired:
                self._global_semaphore.release()


# Helper async context manager for httpx client lifecycle
@asynccontextmanager
async def httpx_client_context():
    import httpx
    async with httpx.AsyncClient() as client:
        yield client


# Global Singleton Manager instance
sandbox_manager = SandboxManager()
