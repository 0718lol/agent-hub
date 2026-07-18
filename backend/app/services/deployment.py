"""Build and publish pipelines for generated projects."""

import asyncio
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

import httpx

from app.core.config import deobfuscate_key, settings
from app.core.file_storage import FileStorageManager
from app.core.workspace import resolve_workspace

MAX_DEPLOY_FILES = 2_000
MAX_DEPLOY_BYTES = 100 * 1024 * 1024
IGNORED_DIRECTORIES = {".git", ".agenthub", "node_modules", ".venv", "venv", "__pycache__"}
DEPLOY_TARGETS = {"auto", "web", "api", "apk", "miniprogram"}
ProgressCallback = Callable[[str, str, int], Awaitable[None]]
CancellationCallback = Callable[[], Awaitable[bool]]


class DeploymentError(RuntimeError):
    """A deployment could not be started or completed."""


class DeploymentCancelled(DeploymentError):
    """A deployment was explicitly cancelled by its owner."""


async def _raise_if_cancelled(cancelled: CancellationCallback | None) -> None:
    if cancelled and await cancelled():
        raise DeploymentCancelled("构建已被用户取消")


async def _await_with_cancel(awaitable, cancelled: CancellationCallback | None):
    task = asyncio.create_task(awaitable)
    try:
        while True:
            await _raise_if_cancelled(cancelled)
            done, _pending = await asyncio.wait({task}, timeout=1)
            if done:
                return task.result()
    except BaseException:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        raise


async def _stop_process(process) -> None:
    if getattr(process, "returncode", None) is not None:
        return
    try:
        process.terminate()
    except (AttributeError, ProcessLookupError):
        pass
    try:
        await asyncio.wait_for(process.wait(), timeout=3)
        return
    except (AttributeError, asyncio.TimeoutError):
        pass
    try:
        process.kill()
    except (AttributeError, ProcessLookupError):
        pass
    try:
        await process.wait()
    except AttributeError:
        pass


async def _communicate_cancellable(
    process,
    *,
    timeout: int,
    action: str,
    cancelled: CancellationCallback | None,
    heartbeat: Callable[[], Awaitable[None]] | None = None,
):
    task = asyncio.create_task(process.communicate())
    deadline = asyncio.get_running_loop().time() + timeout
    next_heartbeat = asyncio.get_running_loop().time() + 20
    try:
        while True:
            await _raise_if_cancelled(cancelled)
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            done, _pending = await asyncio.wait({task}, timeout=min(1, remaining))
            if done:
                return task.result()
            if heartbeat and asyncio.get_running_loop().time() >= next_heartbeat:
                await heartbeat()
                next_heartbeat = asyncio.get_running_loop().time() + 20
    except DeploymentCancelled:
        await _stop_process(process)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise
    except asyncio.TimeoutError as exc:
        await _stop_process(process)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise DeploymentError(f"{action}超时，已终止") from exc


@dataclass(frozen=True)
class DeploymentResult:
    url: str
    provider: str
    target: str = "web"
    result_type: str = "site"
    published: bool = True
    runtime_url: str = ""
    container_name: str = ""


def get_workspace_path(conversation_id: str) -> Path:
    workspace = resolve_workspace(conversation_id, create=False)
    if workspace is None:
        raise DeploymentError("Invalid conversation ID")
    if not workspace.is_dir():
        raise DeploymentError("No generated project was found for this conversation")
    return workspace


def _read_package_json(workspace: Path) -> dict:
    try:
        return json.loads((workspace / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _miniprogram_root(workspace: Path) -> Path | None:
    config_path = workspace / "project.config.json"
    if not config_path.is_file():
        return None
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    relative_root = config.get("miniprogramRoot", "") if isinstance(config, dict) else ""
    candidate = (workspace / relative_root).resolve()
    try:
        candidate.relative_to(workspace.resolve())
    except ValueError:
        return None
    return candidate if (candidate / "app.json").is_file() else None


def detect_project_type(workspace: Path) -> str:
    """Detect a supported target from conventional project files."""
    android_roots = (workspace, workspace / "android")
    if any((root / "gradlew").is_file() and (
        (root / "build.gradle").is_file() or (root / "build.gradle.kts").is_file()
    ) for root in android_roots):
        return "apk"
    if _miniprogram_root(workspace):
        return "miniprogram"
    if (workspace / "Dockerfile").is_file():
        return "api"
    if any((workspace / name).is_file() for name in ("requirements.txt", "pyproject.toml", "go.mod")):
        return "api"

    package = _read_package_json(workspace)
    scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
    dependencies = {
        **(package.get("dependencies", {}) if isinstance(package.get("dependencies"), dict) else {}),
        **(package.get("devDependencies", {}) if isinstance(package.get("devDependencies"), dict) else {}),
    } if isinstance(package, dict) else {}
    if any(name in dependencies for name in ("express", "fastify", "koa", "hono")) or "start:server" in scripts:
        return "api"
    if any((workspace / path / "index.html").is_file() for path in (Path("."), Path("dist"), Path("build"))):
        return "web"
    raise DeploymentError(
        "无法识别项目类型。Web 需要 index.html，API 需要 Dockerfile/服务端清单，"
        "Android 需要 Gradle Wrapper，小程序需要 project.config.json 和 app.json。"
    )


def build_project_archive(workspace: Path) -> bytes:
    """Create a bounded source archive without local dependencies."""
    archive = io.BytesIO()
    file_count = 0
    total_bytes = 0
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in workspace.rglob("*"):
            if not path.is_file() or any(part in IGNORED_DIRECTORIES for part in path.relative_to(workspace).parts):
                continue
            file_count += 1
            total_bytes += path.stat().st_size
            if file_count > MAX_DEPLOY_FILES or total_bytes > MAX_DEPLOY_BYTES:
                raise DeploymentError("Project is too large to package (limit: 2,000 files / 100 MB)")
            bundle.write(path, path.relative_to(workspace).as_posix())
    if file_count == 0:
        raise DeploymentError("Generated project contains no deployable files")
    return archive.getvalue()


def build_static_site_archive(workspace: Path) -> bytes:
    """Backward-compatible static archive helper."""
    return build_project_archive(workspace)


def _web_root(workspace: Path) -> Path:
    for candidate in (workspace / "dist", workspace / "build", workspace):
        if (candidate / "index.html").is_file():
            return candidate
    raise DeploymentError("Web pipeline requires index.html in the project root, dist, or build directory")


def _save_artifact(content: bytes, user_id: str, extension: str) -> str:
    stored_name = f"tenantfile__{user_id}__build_{uuid.uuid4().hex}.{extension.lstrip('.')}"
    FileStorageManager.save(content, stored_name)
    return FileStorageManager.get_url(stored_name)


class NetlifyDeploymentProvider:
    """Publish a static archive through Netlify's Deploy API."""

    name = "netlify"

    def __init__(self, token: str, site_id: str):
        self.token = token
        self.site_id = site_id

    async def deploy(
        self,
        archive: bytes,
        cancelled: CancellationCallback | None = None,
    ) -> DeploymentResult:
        endpoint = f"https://api.netlify.com/api/v1/sites/{self.site_id}/deploys"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/zip"}
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await _await_with_cancel(
                    client.post(endpoint, content=archive, headers=headers), cancelled
                )
        except httpx.HTTPError as exc:
            raise DeploymentError("Could not reach Netlify. Check network access and try again.") from exc
        if response.status_code not in (200, 201):
            detail = response.text[:300].replace("\n", " ")
            raise DeploymentError(f"Netlify rejected the deployment (HTTP {response.status_code}): {detail}")
        payload = response.json()
        url = payload.get("deploy_ssl_url") or payload.get("ssl_url") or payload.get("url")
        if not url:
            raise DeploymentError("Netlify did not return a public deployment URL")
        return DeploymentResult(url=url, provider=self.name)


async def deploy_static_site(conversation_id: str, *, token: str, site_id: str) -> DeploymentResult:
    if not token or not site_id:
        raise DeploymentError(
            "Netlify is not configured. Set AGENTHUB_NETLIFY_TOKEN and AGENTHUB_NETLIFY_SITE_ID."
        )
    workspace = get_workspace_path(conversation_id)
    archive = await asyncio.to_thread(build_project_archive, _web_root(workspace))
    return await NetlifyDeploymentProvider(token, site_id).deploy(archive)


def _android_root(workspace: Path) -> Path:
    for candidate in (workspace, workspace / "android"):
        if (candidate / "gradlew").is_file():
            return candidate
    raise DeploymentError("Android pipeline requires a Gradle Wrapper (gradlew)")


def _latest_apk(android_root: Path) -> Path | None:
    apks = list(android_root.glob("**/build/outputs/apk/**/*.apk"))
    return max(apks, key=lambda path: path.stat().st_mtime) if apks else None


def _clear_existing_apks(android_root: Path) -> None:
    for apk in android_root.glob("**/build/outputs/apk/**/*.apk"):
        apk.unlink(missing_ok=True)


async def _build_apk(
    workspace: Path,
    progress: ProgressCallback,
    cancelled: CancellationCallback | None = None,
) -> bytes:
    await _raise_if_cancelled(cancelled)
    android_root = _android_root(workspace)
    await asyncio.to_thread(_clear_existing_apks, android_root)

    await progress("dependencies", "正在解析 Gradle 和 Android 构建依赖...", 30)
    await progress("build", "执行 Gradle assembleRelease，首次构建可能需要下载 Android 依赖...", 45)
    build_container_name = ""
    if settings.docker_sandbox:
        workspace_key = hashlib.sha256(str(workspace).encode("utf-8")).hexdigest()[:12]
        build_container_name = f"agenthub-apk-build-{workspace_key}"
        if str(android_root).startswith("/agenthub_export/"):
            project_subpath = workspace.relative_to("/agenthub_export").as_posix()
            android_subpath = android_root.relative_to(workspace).as_posix()
            mount = (
                f"type=volume,src={settings.generated_projects_volume},dst=/workspace,"
                f"volume-subpath={project_subpath}"
            )
            build_dir = "/workspace" if android_subpath == "." else f"/workspace/{android_subpath}"
        else:
            mount = f"type=bind,src={workspace},dst=/workspace"
            android_subpath = android_root.relative_to(workspace).as_posix()
            build_dir = "/workspace" if android_subpath == "." else f"/workspace/{android_subpath}"
        command = [
            "docker", "run", "--rm",
            "--name", build_container_name,
            "--network", "bridge",
            "--memory", "3g",
            "--cpus", "2.0",
            "--pids-limit", "256",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--tmpfs", "/tmp:rw,nosuid,size=512m",
            "--mount", mount,
            "-w", build_dir,
            settings.builder_image,
            "/bin/sh", "gradlew", "assembleRelease", "--no-daemon",
        ]
        cwd = None
    elif settings.allow_unsandboxed_shell:
        command = ["/bin/sh", "gradlew", "assembleRelease", "--no-daemon"]
        cwd = android_root
    else:
        raise DeploymentError("没有可用的隔离构建环境，禁止在主机直接执行 Gradle")
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "CI": "true"},
        )
        async def heartbeat():
            await progress("build", "Gradle 仍在构建 APK，请稍候...", 58)

        output, _ = await _communicate_cancellable(
            process,
            timeout=600,
            action="APK 构建",
            cancelled=cancelled,
            heartbeat=heartbeat,
        )
    except DeploymentCancelled:
        if build_container_name and await _container_exists(build_container_name):
            await _run_docker_command(
                ["docker", "rm", "-f", build_container_name],
                30,
                "清理已取消的 APK 构建容器",
            )
        raise
    except FileNotFoundError as exc:
        raise DeploymentError("无法启动 Gradle，请检查 JDK 和 Android SDK 是否已安装") from exc
    if process.returncode != 0:
        tail = output.decode("utf-8", errors="replace")[-1200:]
        raise DeploymentError(f"Gradle 构建失败：\n{tail}")
    apk = await asyncio.to_thread(_latest_apk, android_root)
    if not apk:
        raise DeploymentError("Gradle 执行成功，但没有找到 APK 构建产物")
    return await asyncio.to_thread(apk.read_bytes)


def _detect_api_port(workspace: Path) -> int:
    dockerfile = (workspace / "Dockerfile").read_text(encoding="utf-8", errors="replace")
    match = re.search(r"(?im)^\s*EXPOSE\s+(\d{2,5})(?:/tcp)?\s*$", dockerfile)
    port = int(match.group(1)) if match else 8000
    if port < 1024 or port > 65535:
        raise DeploymentError("API container must expose an unprivileged port between 1024 and 65535")
    return port


async def _run_docker_command(
    command: list[str],
    timeout: int,
    action: str,
    cancelled: CancellationCallback | None = None,
) -> str:
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await _communicate_cancellable(
            process,
            timeout=timeout,
            action=action,
            cancelled=cancelled,
        )
    except FileNotFoundError as exc:
        raise DeploymentError("构建 Worker 未安装 Docker CLI") from exc
    text = output.decode("utf-8", errors="replace")
    if process.returncode != 0:
        raise DeploymentError(f"{action}失败：\n{text[-1600:]}")
    return text.strip()


def _clear_web_build_outputs(workspace: Path) -> None:
    for directory in (workspace / "dist", workspace / "build"):
        if directory.is_dir():
            shutil.rmtree(directory)


async def _build_web_project(
    workspace: Path,
    progress: ProgressCallback,
    cancelled: CancellationCallback | None = None,
) -> Path:
    package = _read_package_json(workspace)
    scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
    if not isinstance(scripts, dict) or not scripts.get("build"):
        return _web_root(workspace)

    await _raise_if_cancelled(cancelled)
    await asyncio.to_thread(_clear_web_build_outputs, workspace)
    install = "npm ci" if (workspace / "package-lock.json").is_file() else "npm install"
    await progress("dependencies", "正在隔离安装 Web 依赖...", 32)

    if settings.docker_sandbox:
        suffix = hashlib.sha256(str(workspace).encode("utf-8")).hexdigest()[:12]
        if str(workspace).startswith("/agenthub_export/"):
            project_subpath = workspace.relative_to("/agenthub_export").as_posix()
            mount = (
                f"type=volume,src={settings.generated_projects_volume},dst=/workspace,"
                f"volume-subpath={project_subpath}"
            )
        else:
            mount = f"type=bind,src={workspace},dst=/workspace"
        command = [
            "docker", "run", "--rm",
            "--name", f"agenthub-web-build-{suffix}",
            "--network", settings.runtime_dependency_network,
            "--memory", settings.deployment_build_memory,
            "--cpus", settings.deployment_build_cpus,
            "--pids-limit", str(settings.deployment_build_pids),
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--tmpfs", "/tmp:rw,nosuid,size=1024m",
            "--mount", mount,
            "-w", "/workspace",
            "-e", "HOME=/tmp",
            "-e", "npm_config_cache=/tmp/.npm",
            settings.runtime_sandbox_image,
            "sh", "-lc",
            f"{install} --no-audit --no-fund && npm run build",
        ]
        await _run_docker_command(command, 600, "Web 项目构建", cancelled)
    elif settings.allow_unsandboxed_shell:
        process = await asyncio.create_subprocess_exec(
            *install.split(), "--no-audit", "--no-fund",
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await _communicate_cancellable(
            process, timeout=300, action="Web 依赖安装", cancelled=cancelled
        )
        if process.returncode != 0:
            raise DeploymentError(output.decode("utf-8", errors="replace")[-1600:])
        process = await asyncio.create_subprocess_exec(
            "npm", "run", "build",
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await _communicate_cancellable(
            process, timeout=300, action="Web 项目构建", cancelled=cancelled
        )
        if process.returncode != 0:
            raise DeploymentError(output.decode("utf-8", errors="replace")[-1600:])
    else:
        raise DeploymentError("没有可用的隔离构建环境，禁止在主机直接执行 Web 构建")

    await progress("build", "Web 项目编译完成，正在校验发布产物...", 62)
    for candidate in (workspace / "dist", workspace / "build"):
        if (candidate / "index.html").is_file():
            return candidate
    raise DeploymentError("Web 构建完成但未找到 dist/index.html 或 build/index.html")


async def _deploy_api_container(
    workspace: Path,
    deployment_id: str,
    progress: ProgressCallback,
    cancelled: CancellationCallback | None = None,
) -> DeploymentResult:
    await _raise_if_cancelled(cancelled)
    if not re.fullmatch(r"[a-f0-9]{16,64}", deployment_id):
        raise DeploymentError("Invalid deployment ID")
    if not (workspace / "Dockerfile").is_file():
        raise DeploymentError("API 公网发布需要 Dockerfile，请先让 DevOps Agent 生成容器配置")

    # Enforce archive limits before passing a generated build context to Docker.
    await asyncio.to_thread(build_project_archive, workspace)
    port = _detect_api_port(workspace)
    suffix = deployment_id[:16]
    image_name = f"agenthub-generated-api:{suffix}"
    container_name = f"agenthub-api-{suffix}"
    await progress("dependencies", "正在校验 Dockerfile、端口和服务依赖...", 30)
    await progress("build", "正在隔离构建 API 容器镜像...", 45)
    try:
        cpu_quota = max(10_000, int(float(settings.deployment_build_cpus) * 100_000))
    except ValueError as exc:
        raise DeploymentError("Invalid deployment build CPU limit") from exc
    await _run_docker_command(
        [
            "docker", "build", "--pull=false",
            "--network", settings.deployment_build_network,
            "--memory", settings.deployment_build_memory,
            "--cpu-period", "100000",
            "--cpu-quota", str(cpu_quota),
            "--shm-size", "256m",
            "--label", "agenthub.managed=true",
            "--label", f"agenthub.deployment={deployment_id}",
            "-t", image_name, str(workspace),
        ],
        600,
        "API 镜像构建",
        cancelled,
    )
    if await _container_exists(container_name):
        await _run_docker_command(
            ["docker", "rm", "-f", container_name], 30, "清理旧 API 容器", cancelled
        )
    await progress("upload", "镜像构建完成，正在启动受限 API 运行实例...", 76)
    try:
        await _run_docker_command(
            [
                "docker", "run", "-d",
                "--name", container_name,
                "--restart", "unless-stopped",
                "--label", "agenthub.managed=true",
                "--label", f"agenthub.deployment={deployment_id}",
                "--network", settings.runtime_network,
                "--memory", settings.api_runtime_memory,
                "--cpus", settings.api_runtime_cpus,
                "--pids-limit", str(settings.api_runtime_pids),
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges:true",
                "--read-only",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
                "--user", "65532:65532",
                "-e", "PYTHONDONTWRITEBYTECODE=1",
                image_name,
            ],
            60,
            "API 容器启动",
            cancelled,
        )
    except DeploymentCancelled:
        if await _container_exists(container_name):
            await _run_docker_command(
                ["docker", "rm", "-f", container_name], 30, "清理已取消的 API 容器"
            )
        raise
    runtime_url = f"http://{container_name}:{port}"
    await progress("upload", "API 容器已启动，正在执行发布可用性检查...", 88)
    async with httpx.AsyncClient(timeout=2.0) as client:
        for _ in range(15):
            try:
                await _raise_if_cancelled(cancelled)
            except DeploymentCancelled:
                await _run_docker_command(
                    ["docker", "rm", "-f", container_name], 30, "清理已取消的 API 容器"
                )
                raise
            try:
                response = await client.get(runtime_url + "/")
                if response.status_code < 500:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        else:
            await _run_docker_command(["docker", "rm", "-f", container_name], 30, "清理失败容器")
            raise DeploymentError("API 容器启动后未通过可用性检查，请确认 EXPOSE 端口和启动命令")

    public_path = f"/published/{deployment_id}/"
    public_url = settings.public_base_url.rstrip("/") + public_path if settings.public_base_url else public_path
    return DeploymentResult(
        url=public_url,
        provider="docker-runtime",
        target="api",
        result_type="site",
        published=True,
        runtime_url=runtime_url,
        container_name=container_name,
    )


async def _container_exists(container_name: str) -> bool:
    try:
        process = await asyncio.create_subprocess_exec(
            "docker", "container", "inspect", container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(process.wait(), timeout=10)
        return process.returncode == 0
    except (FileNotFoundError, asyncio.TimeoutError):
        return False


async def _run_trusted_command(
    command: list[str],
    timeout: int,
    action: str,
    cancelled: CancellationCallback | None = None,
) -> str:
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await _communicate_cancellable(
            process,
            timeout=timeout,
            action=action,
            cancelled=cancelled,
        )
    except FileNotFoundError as exc:
        raise DeploymentError(f"{action}无法执行或超时") from exc
    text = output.decode("utf-8", errors="replace")
    if process.returncode != 0:
        raise DeploymentError(f"{action}失败：{text[-1200:]}")
    return text


def _owned_secret_path(user_id: str, file_id: str) -> Path:
    if not file_id.startswith(f"tenantfile__{user_id}__") or not FileStorageManager.exists(file_id):
        raise DeploymentError("签名或上传凭证不存在")
    return Path(FileStorageManager.get_absolute_path(file_id))


async def _sign_apk(
    apk: bytes,
    conversation_id: str,
    user_id: str,
    options: dict,
    progress: ProgressCallback,
    cancelled: CancellationCallback | None = None,
) -> bytes:
    await _raise_if_cancelled(cancelled)
    mode = options.get("signing_mode", "")
    if not mode:
        return apk
    signing_dir = Path(FileStorageManager.get_absolute_path("signing"))
    signing_dir.mkdir(parents=True, exist_ok=True)
    if mode == "demo":
        key_id = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:24]
        keystore = signing_dir / f"demo_{key_id}.jks"
        alias = "agenthub-demo"
        store_password = key_password = "agenthub-demo-password"
        if not keystore.exists():
            try:
                await _run_trusted_command([
                    "keytool", "-genkeypair", "-noprompt",
                    "-keystore", str(keystore), "-storepass", store_password,
                    "-keypass", key_password, "-alias", alias,
                    "-keyalg", "RSA", "-keysize", "2048", "-validity", "3650",
                    "-dname", "CN=AgentHub Demo, OU=Demo, O=AgentHub, C=CN",
                ], 60, "生成演示签名", cancelled)
            except DeploymentCancelled:
                keystore.unlink(missing_ok=True)
                raise
        await progress("sign", "正在使用系统演示密钥签名 APK（仅用于测试安装）...", 74)
    elif mode == "uploaded":
        keystore = await asyncio.to_thread(
            _owned_secret_path, user_id, options.get("keystore_file_id", "")
        )
        alias = options.get("key_alias", "")
        store_password = deobfuscate_key(options.get("store_password", ""))
        key_password = deobfuscate_key(options.get("key_password", "")) or store_password
        if not alias or not store_password:
            raise DeploymentError("用户 keystore 缺少别名或密码")
        await progress("sign", "正在使用用户 keystore 签名 APK...", 74)
    else:
        raise DeploymentError("Unsupported APK signing mode")

    sdk_root = Path(os.environ.get("ANDROID_SDK_ROOT", "/opt/android-sdk"))
    signers = sorted(sdk_root.glob("build-tools/*/apksigner"), reverse=True)
    if not signers:
        raise DeploymentError("构建节点缺少 Android apksigner")
    with tempfile.TemporaryDirectory(prefix="agenthub-sign-") as temp:
        unsigned = Path(temp) / "unsigned.apk"
        signed = Path(temp) / "signed.apk"
        unsigned.write_bytes(apk)
        sign_command = [
            str(signers[0]), "sign",
            "--ks", str(keystore), "--ks-key-alias", alias,
            "--ks-pass", f"pass:{store_password}",
            "--key-pass", f"pass:{key_password}",
        ]
        if keystore.suffix.lower() in {".p12", ".pfx"}:
            sign_command.extend(["--ks-type", "PKCS12"])
        sign_command.extend(["--out", str(signed), str(unsigned)])
        await _run_trusted_command(sign_command, 60, "APK 签名", cancelled)
        await _run_trusted_command(
            [str(signers[0]), "verify", str(signed)], 30, "APK 签名校验", cancelled
        )
        return signed.read_bytes()


async def _upload_miniprogram(
    workspace: Path,
    user_id: str,
    options: dict,
    progress: ProgressCallback,
    cancelled: CancellationCallback | None = None,
) -> None:
    await _raise_if_cancelled(cancelled)
    appid = options.get("mini_appid", "")
    private_key_id = options.get("mini_private_key_file_id", "")
    if not appid or not private_key_id:
        raise DeploymentError("微信小程序凭证尚未配置")
    if not re.fullmatch(r"wx[a-fA-F0-9]{16}", appid):
        raise DeploymentError("微信小程序 AppID 格式不正确")
    version = options.get("version", "1.0.0")
    if not re.fullmatch(r"[0-9A-Za-z._-]{1,32}", version):
        raise DeploymentError("小程序版本号格式不正确")
    private_key = await asyncio.to_thread(_owned_secret_path, user_id, private_key_id)
    script = Path(__file__).resolve().parents[1] / "scripts" / "miniprogram_upload.js"
    await progress("upload", f"正在通过微信 miniprogram-ci 上传版本 {version}...", 82)
    await _run_trusted_command([
        "node", str(script), "upload", str(workspace), appid, str(private_key), version,
        options.get("description", "AgentHub 发布"), "",
    ], 600, "微信小程序上传", cancelled)


async def _preview_miniprogram(
    workspace: Path,
    user_id: str,
    options: dict,
    progress: ProgressCallback,
    cancelled: CancellationCallback | None = None,
) -> str:
    await _raise_if_cancelled(cancelled)
    appid = options.get("mini_appid", "")
    private_key_id = options.get("mini_private_key_file_id", "")
    if not appid or not private_key_id:
        raise DeploymentError("生成体验二维码需要微信 AppID 和代码上传私钥")
    if not re.fullmatch(r"wx[a-fA-F0-9]{16}", appid):
        raise DeploymentError("微信小程序 AppID 格式不正确")
    private_key = await asyncio.to_thread(_owned_secret_path, user_id, private_key_id)
    script = Path(__file__).resolve().parents[1] / "scripts" / "miniprogram_upload.js"
    await progress("upload", "正在通过微信 miniprogram-ci 编译体验版并生成二维码...", 82)
    with tempfile.TemporaryDirectory(prefix="agenthub-mini-preview-") as temp:
        qrcode_path = Path(temp) / "preview.jpg"
        await _run_trusted_command([
            "node", str(script), "preview", str(workspace), appid, str(private_key),
            options.get("version", "1.0.0"),
            options.get("description", "AgentHub 体验预览"),
            str(qrcode_path),
        ], 600, "微信小程序体验版预览", cancelled)
        if not qrcode_path.is_file() or qrcode_path.stat().st_size == 0:
            raise DeploymentError("微信编译成功，但没有生成体验二维码")
        return await asyncio.to_thread(_save_artifact, qrcode_path.read_bytes(), user_id, "jpg")


async def run_deployment_pipeline(
    conversation_id: str,
    *,
    user_id: str,
    target: str,
    token: str,
    site_id: str,
    progress: ProgressCallback,
    deployment_id: str = "",
    options: dict | None = None,
    cancelled: CancellationCallback | None = None,
) -> DeploymentResult:
    """Detect, build, package, and optionally publish one generated project."""
    if target not in DEPLOY_TARGETS:
        raise DeploymentError(f"Unsupported deployment target: {target}")
    await _raise_if_cancelled(cancelled)
    workspace = get_workspace_path(conversation_id)
    options = options or {}
    detected = await asyncio.to_thread(detect_project_type, workspace)
    await _raise_if_cancelled(cancelled)
    selected = detected if target == "auto" else target
    await progress("generate", f"项目识别完成：{detected}；执行 {selected} 流水线。", 20)

    if target != "auto" and target != detected:
        await progress("generate", f"已按手动选择覆盖自动识别结果（{detected}）。", 22)

    if selected == "web":
        await progress("dependencies", "正在检查 Web 工程和发布目录...", 28)
        root = await _build_web_project(workspace, progress, cancelled)
        archive = await asyncio.to_thread(build_project_archive, root)
        await _raise_if_cancelled(cancelled)
        await progress("build", "Web 发布产物校验和压缩完成。", 68)
        if token and site_id:
            await progress("upload", "正在上传 Netlify CDN...", 82)
            return await NetlifyDeploymentProvider(token, site_id).deploy(archive, cancelled)
        url = await asyncio.to_thread(_save_artifact, archive, user_id, "zip")
        await progress("upload", "未配置 Netlify，已保存可下载的 Web 发布包。", 92)
        return DeploymentResult(url=url, provider="artifact", target="web", result_type="download", published=False)

    if selected == "api":
        if deployment_id:
            return await _deploy_api_container(
                workspace, deployment_id, progress, cancelled
            )
        await progress("dependencies", "正在检查 API 服务清单和依赖文件...", 30)
        archive = await asyncio.to_thread(build_project_archive, workspace)
        await _raise_if_cancelled(cancelled)
        url = await asyncio.to_thread(_save_artifact, archive, user_id, "zip")
        await progress("build", "API 工程校验完成，已生成服务部署包。", 72)
        await progress("upload", "API 服务部署包已保存。", 92)
        return DeploymentResult(url=url, provider="artifact", target="api", result_type="download", published=False)

    if selected == "apk":
        apk = await _build_apk(workspace, progress, cancelled)
        apk = await _sign_apk(
            apk, conversation_id, user_id, options, progress, cancelled
        )
        if len(apk) > MAX_DEPLOY_BYTES:
            raise DeploymentError("APK exceeds the 100 MB artifact limit")
        url = await asyncio.to_thread(_save_artifact, apk, user_id, "apk")
        await progress("upload", "APK 已保存，正在生成受权限保护的下载链接。", 92)
        return DeploymentResult(url=url, provider="gradle", target="apk", result_type="download", published=True)

    if not _miniprogram_root(workspace):
        raise DeploymentError("微信小程序工程缺少 project.config.json 或 app.json")
    await progress("dependencies", "正在校验小程序配置、资源和上传依赖...", 30)
    archive = await asyncio.to_thread(build_project_archive, workspace)
    await _raise_if_cancelled(cancelled)
    await progress("build", "微信小程序工程检查和打包完成。", 62)
    if options.get("mini_appid") and options.get("mini_private_key_file_id"):
        if options.get("mini_action") == "preview":
            url = await _preview_miniprogram(
                workspace, user_id, options, progress, cancelled
            )
            await progress("upload", "体验版二维码已生成，请使用微信扫码预览。", 94)
            return DeploymentResult(
                url=url, provider="miniprogram-ci", target="miniprogram",
                result_type="miniprogram-preview", published=False,
            )
        await _upload_miniprogram(
            workspace, user_id, options, progress, cancelled
        )
        url = await asyncio.to_thread(_save_artifact, archive, user_id, "zip")
        await progress("upload", "微信小程序代码上传成功，可前往微信公众平台提交体验或审核。", 94)
        return DeploymentResult(
            url=url, provider="miniprogram-ci", target="miniprogram",
            result_type="miniprogram", published=True,
        )
    url = await asyncio.to_thread(_save_artifact, archive, user_id, "zip")
    await progress("upload", "凭证尚未配置，已生成开发者工具上传包。", 92)
    return DeploymentResult(
        url=url, provider="wechat-awaiting-config", target="miniprogram", result_type="download", published=False
    )
