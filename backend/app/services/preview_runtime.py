"""Isolated development-server runtimes for generated Web projects."""

import asyncio
import hashlib
import json
import re
import shlex
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.tenancy import conversation_user_id

PREVIEW_PORT = 4173
_RUNTIME_URL = re.compile(
    r"^http://(?:127\.0\.0\.1:\d{2,5}|agenthub-preview-[a-f0-9]{16}:4173)$"
)


class PreviewRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreviewRuntime:
    conversation_id: str
    container_name: str
    runtime_url: str
    public_path: str
    started_at: float


class PreviewRuntimeManager:
    def __init__(self):
        self._runtimes: dict[str, PreviewRuntime] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._admission_lock = asyncio.Lock()
        self._capability_checked_at = 0.0
        self._docker_available = False

    async def _docker(self, *args: str, timeout: int = 30, check: bool = True) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                "docker",
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            output, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except FileNotFoundError as exc:
            raise PreviewRuntimeError("Docker CLI 未安装，无法启动隔离预览") from exc
        except TimeoutError as exc:
            raise PreviewRuntimeError("Docker 预览操作超时") from exc
        text = output.decode("utf-8", errors="replace")
        if check and process.returncode != 0:
            raise PreviewRuntimeError(text[-1600:].strip() or "Docker 预览操作失败")
        return text.strip()

    async def _running_preview_containers(self, tenant_hash: str | None = None) -> list[str]:
        args = ["ps", "--filter", "label=agenthub.preview=true"]
        if tenant_hash:
            args.extend(["--filter", f"label=agenthub.preview-tenant={tenant_hash}"])
        args.extend(["--format", "{{.Names}}"])
        output = await self._docker(*args, timeout=15, check=False)
        return [name.strip() for name in output.splitlines() if name.strip()]

    async def _oldest_container(self, names: list[str]) -> str | None:
        created = []
        for name in names:
            timestamp = await self._docker(
                "inspect", "--format", "{{.Created}}", name, timeout=10, check=False
            )
            if timestamp:
                created.append((timestamp, name))
        return min(created)[1] if created else (names[-1] if names else None)

    async def _forget_container(self, container_name: str) -> None:
        await self._docker("rm", "-f", container_name, timeout=15, check=False)
        for conversation_id, runtime in list(self._runtimes.items()):
            if runtime.container_name == container_name:
                self._runtimes.pop(conversation_id, None)

    async def _enforce_docker_quotas(self, tenant_hash: str) -> None:
        tenant_names = await self._running_preview_containers(tenant_hash)
        while len(tenant_names) >= max(1, settings.preview_runtime_max_per_tenant):
            victim = await self._oldest_container(tenant_names)
            if not victim:
                break
            await self._forget_container(victim)
            tenant_names.remove(victim)

        all_names = await self._running_preview_containers()
        while len(all_names) >= max(1, settings.preview_runtime_max_total):
            victim = await self._oldest_container(all_names)
            if not victim:
                break
            await self._forget_container(victim)
            all_names.remove(victim)

    async def docker_available(self) -> bool:
        now = time.monotonic()
        if now - self._capability_checked_at < 15:
            return self._docker_available
        try:
            await self._docker("info", timeout=3)
            await self._docker("image", "inspect", settings.runtime_sandbox_image, timeout=5)
            self._docker_available = True
        except PreviewRuntimeError:
            self._docker_available = False
        self._capability_checked_at = now
        return self._docker_available

    @staticmethod
    def supports_vite(workspace: Path) -> bool:
        try:
            package = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        scripts = package.get("scripts", {})
        dependencies_data = package.get("dependencies", {})
        dev_dependencies_data = package.get("devDependencies", {})
        dependencies = {
            **(dependencies_data if isinstance(dependencies_data, dict) else {}),
            **(dev_dependencies_data if isinstance(dev_dependencies_data, dict) else {}),
        }
        return isinstance(scripts, dict) and "dev" in scripts and "vite" in dependencies

    @staticmethod
    def _mount(workspace: Path) -> tuple[str, bool]:
        generated_root = Path("/agenthub_export")
        try:
            subpath = workspace.relative_to(generated_root).as_posix()
        except ValueError:
            return f"type=bind,src={workspace},dst=/workspace,readonly", False
        return (
            f"type=volume,src={settings.generated_projects_volume},dst=/workspace,"
            f"volume-subpath={subpath},readonly",
            True,
        )

    async def start(self, conversation_id: str, public_conversation_id: str, workspace: Path) -> PreviewRuntime:
        if not self.supports_vite(workspace):
            raise PreviewRuntimeError("当前项目不是可识别的 Vite 工程，已保留静态文件预览")
        if not await self.docker_available():
            raise PreviewRuntimeError("隔离预览环境不可用，请启动 Docker 和 runtime-sandbox-image")

        lock = self._locks.setdefault(conversation_id, asyncio.Lock())
        async with lock:
            await self.stop(conversation_id)
            async with self._admission_lock:
                tenant_id = conversation_user_id(conversation_id) or "anonymous"
                tenant_hash = hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:24]
                tenant_runtimes = [
                    runtime for runtime in self._runtimes.values()
                    if (conversation_user_id(runtime.conversation_id) or "anonymous") == tenant_id
                ]
                while len(tenant_runtimes) >= max(1, settings.preview_runtime_max_per_tenant):
                    oldest = min(tenant_runtimes, key=lambda item: item.started_at)
                    await self.stop(oldest.conversation_id)
                    tenant_runtimes.remove(oldest)
                while len(self._runtimes) >= max(1, settings.preview_runtime_max_total):
                    oldest = min(self._runtimes.values(), key=lambda item: item.started_at)
                    await self.stop(oldest.conversation_id)
                await self._enforce_docker_quotas(tenant_hash)
            suffix = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:16]
            container_name = f"agenthub-preview-{suffix}"
            public_path = f"/api/previews/{public_conversation_id}/runtime/"
            mount, use_internal_network = self._mount(workspace)
            install = "npm ci" if (workspace / "package-lock.json").is_file() else "npm install"
            command = " && ".join([
                "cp -R /workspace/. /tmp/app",
                "cd /tmp/app",
                f"{install} --no-audit --no-fund",
                (
                    "npm run dev -- --host 0.0.0.0 "
                    f"--port {PREVIEW_PORT} --base {shlex.quote(public_path)}"
                ),
            ])
            docker_args = [
                "run", "-d", "--name", container_name,
                "--label", "agenthub.managed=true",
                "--label", "agenthub.preview=true",
                "--label", f"agenthub.preview-tenant={tenant_hash}",
                "--label", f"agenthub.preview-path={public_path}",
                "--network", "bridge",
                "--memory", settings.runtime_sandbox_memory,
                "--cpus", settings.runtime_sandbox_cpus,
                "--pids-limit", str(settings.runtime_sandbox_pids),
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges:true",
                "--read-only",
                "--tmpfs", "/tmp:rw,nosuid,size=1024m",  # nosec B108
                "--user", "65532:65532",
                "-e", "HOME=/tmp",
                "-e", "npm_config_cache=/tmp/.npm",
                "--mount", mount,
            ]
            if not use_internal_network:
                docker_args.extend(["-p", f"127.0.0.1::{PREVIEW_PORT}"])
            docker_args.extend([
                settings.runtime_sandbox_image,
                "sh", "-lc", command,
            ])
            await self._docker(*docker_args, timeout=30)

            try:
                if use_internal_network:
                    await self._docker(
                        "network", "connect", settings.runtime_network, container_name, timeout=15
                    )
                    runtime_url = f"http://{container_name}:{PREVIEW_PORT}"
                else:
                    mapped = await self._docker("port", container_name, f"{PREVIEW_PORT}/tcp")
                    match = re.search(r"127\.0\.0\.1:(\d{2,5})", mapped)
                    if not match:
                        raise PreviewRuntimeError("无法确定本地预览端口")
                    runtime_url = f"http://127.0.0.1:{match.group(1)}"

                async with httpx.AsyncClient(timeout=2.0) as client:
                    for _ in range(90):
                        try:
                            response = await client.get(runtime_url + public_path)
                            if response.status_code < 500:
                                break
                        except httpx.HTTPError:
                            pass
                        await asyncio.sleep(1)
                    else:
                        logs = await self._docker("logs", "--tail", "80", container_name, check=False)
                        raise PreviewRuntimeError(f"Vite 预览启动失败：\n{logs[-1600:]}")

                runtime = PreviewRuntime(
                    conversation_id=conversation_id,
                    container_name=container_name,
                    runtime_url=runtime_url,
                    public_path=public_path,
                    started_at=time.time(),
                )
                self._runtimes[conversation_id] = runtime
                return runtime
            except Exception:
                await self._docker("rm", "-f", container_name, timeout=15, check=False)
                raise

    async def stop(self, conversation_id: str) -> None:
        runtime = self._runtimes.pop(conversation_id, None)
        suffix = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:16]
        container_name = runtime.container_name if runtime else f"agenthub-preview-{suffix}"
        try:
            await self._docker("rm", "-f", container_name, timeout=15, check=False)
        except PreviewRuntimeError:
            pass

    def get(self, conversation_id: str) -> PreviewRuntime | None:
        return self._runtimes.get(conversation_id)

    async def get_or_discover(
        self,
        conversation_id: str,
        public_conversation_id: str,
        workspace: Path,
    ) -> PreviewRuntime | None:
        runtime = self._runtimes.get(conversation_id)
        suffix = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:16]
        container_name = f"agenthub-preview-{suffix}"
        try:
            running = await self._docker(
                "inspect", "--format", "{{.State.Running}}", container_name,
                timeout=10, check=False,
            )
        except PreviewRuntimeError:
            return runtime
        if running.strip() != "true":
            self._runtimes.pop(conversation_id, None)
            return None
        if runtime is not None:
            return runtime

        public_path = f"/api/previews/{public_conversation_id}/runtime/"
        _mount, use_internal_network = self._mount(workspace)
        if use_internal_network:
            runtime_url = f"http://{container_name}:{PREVIEW_PORT}"
        else:
            mapped = await self._docker(
                "port", container_name, f"{PREVIEW_PORT}/tcp", timeout=10, check=False
            )
            match = re.search(r"127\.0\.0\.1:(\d{2,5})", mapped)
            if not match:
                return None
            runtime_url = f"http://127.0.0.1:{match.group(1)}"
        runtime = PreviewRuntime(
            conversation_id=conversation_id,
            container_name=container_name,
            runtime_url=runtime_url,
            public_path=public_path,
            started_at=time.time(),
        )
        self._runtimes[conversation_id] = runtime
        return runtime

    async def stop_all(self) -> None:
        for conversation_id in list(self._runtimes):
            await self.stop(conversation_id)


preview_runtime_manager = PreviewRuntimeManager()


def validate_runtime_url(url: str) -> bool:
    return bool(_RUNTIME_URL.fullmatch(url))
