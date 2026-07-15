"""Tests for static-site deployment preparation and provider responses."""

import asyncio
from pathlib import Path

import pytest

from app.services.deployment import (
    DeploymentCancelled,
    DeploymentError,
    NetlifyDeploymentProvider,
    _build_apk,
    _run_docker_command,
    _sign_apk,
    build_static_site_archive,
    detect_project_type,
    run_deployment_pipeline,
)


def test_static_archive_excludes_node_modules(tmp_path: Path):
    (tmp_path / "index.html").write_text("<h1>hello</h1>", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "large.js").write_text("ignored", encoding="utf-8")

    archive = build_static_site_archive(tmp_path)

    import zipfile
    from io import BytesIO
    with zipfile.ZipFile(BytesIO(archive)) as bundle:
        assert bundle.namelist() == ["index.html"]


@pytest.mark.asyncio
async def test_netlify_provider_returns_real_url(monkeypatch):
    class Response:
        status_code = 201
        def json(self):
            return {"deploy_ssl_url": "https://demo.netlify.app"}

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        async def post(self, url, content, headers):
            assert url.endswith("/sites/site-1/deploys")
            assert headers["Content-Type"] == "application/zip"
            return Response()

    monkeypatch.setattr("app.services.deployment.httpx.AsyncClient", lambda **_kwargs: Client())
    result = await NetlifyDeploymentProvider("token", "site-1").deploy(b"zip")
    assert result.url == "https://demo.netlify.app"


@pytest.mark.asyncio
async def test_netlify_provider_raises_for_rejected_deploy(monkeypatch):
    class Response:
        status_code = 401
        text = "invalid token"

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        async def post(self, *_args, **_kwargs): return Response()

    monkeypatch.setattr("app.services.deployment.httpx.AsyncClient", lambda **_kwargs: Client())
    with pytest.raises(DeploymentError, match="HTTP 401"):
        await NetlifyDeploymentProvider("token", "site-1").deploy(b"zip")


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({"index.html": "<h1>Web</h1>"}, "web"),
        ({"Dockerfile": "FROM python:3.12", "app.py": ""}, "api"),
        ({"gradlew": "#!/bin/sh", "build.gradle": "plugins {}"}, "apk"),
        ({"project.config.json": "{}", "app.json": "{}"}, "miniprogram"),
    ],
)
def test_detects_supported_project_types(tmp_path: Path, files: dict[str, str], expected: str):
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")

    assert detect_project_type(tmp_path) == expected


def test_detects_built_web_output(tmp_path: Path):
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "index.html").write_text("<h1>Built</h1>", encoding="utf-8")

    assert detect_project_type(tmp_path) == "web"


def test_detects_miniprogram_in_configured_subdirectory(tmp_path: Path):
    (tmp_path / "project.config.json").write_text(
        '{"miniprogramRoot": "src/miniprogram/"}', encoding="utf-8"
    )
    (tmp_path / "src" / "miniprogram").mkdir(parents=True)
    (tmp_path / "src" / "miniprogram" / "app.json").write_text("{}", encoding="utf-8")

    assert detect_project_type(tmp_path) == "miniprogram"


def test_rejects_unknown_project_type(tmp_path: Path):
    (tmp_path / "notes.txt").write_text("unknown", encoding="utf-8")

    with pytest.raises(DeploymentError, match="无法识别项目类型"):
        detect_project_type(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target", "files", "provider"),
    [
        ("web", {"index.html": "<h1>Web</h1>"}, "artifact"),
        ("api", {"Dockerfile": "FROM python:3.12", "app.py": ""}, "artifact"),
        ("miniprogram", {"project.config.json": "{}", "app.json": "{}"}, "wechat-awaiting-config"),
    ],
)
async def test_artifact_pipelines_return_downloads(
    tmp_path: Path, monkeypatch, target: str, files: dict[str, str], provider: str
):
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    logs = []

    async def progress(stage: str, message: str, percent: int):
        logs.append((stage, message, percent))

    monkeypatch.setattr("app.services.deployment.get_workspace_path", lambda _conversation_id: tmp_path)
    monkeypatch.setattr(
        "app.services.deployment._save_artifact", lambda _content, _user_id, extension: f"/uploads/build.{extension}"
    )
    result = await run_deployment_pipeline(
        "conversation", user_id="user", target="auto", token="", site_id="", progress=progress
    )

    assert result.target == target
    assert result.provider == provider
    assert result.result_type == "download"
    assert result.url.startswith("/uploads/")
    assert logs


@pytest.mark.asyncio
async def test_apk_pipeline_reuses_existing_build(tmp_path: Path, monkeypatch):
    (tmp_path / "gradlew").write_text("#!/bin/sh", encoding="utf-8")
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    apk_path = tmp_path / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
    apk_path.parent.mkdir(parents=True)
    apk_path.write_bytes(b"valid-apk-placeholder")

    async def progress(*_args):
        return None

    monkeypatch.setattr("app.services.deployment.get_workspace_path", lambda _conversation_id: tmp_path)
    monkeypatch.setattr(
        "app.services.deployment._save_artifact", lambda _content, _user_id, _extension: "/uploads/app.apk"
    )
    result = await run_deployment_pipeline(
        "conversation", user_id="user", target="auto", token="", site_id="", progress=progress
    )

    assert result.target == "apk"
    assert result.provider == "gradle"
    assert result.url == "/uploads/app.apk"


@pytest.mark.asyncio
async def test_api_pipeline_builds_restricted_runtime(tmp_path: Path, monkeypatch):
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\nEXPOSE 8080\nCMD [\"python\", \"app.py\"]\n",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text("print('server')", encoding="utf-8")
    commands = []

    async def progress(*_args):
        return None

    async def run_command(command, _timeout, _action, *_args):
        commands.append(command)
        return "ok"

    class Response:
        status_code = 200

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        async def get(self, url):
            assert url.endswith(":8080/")
            return Response()

    monkeypatch.setattr("app.services.deployment.get_workspace_path", lambda _conversation_id: tmp_path)
    monkeypatch.setattr("app.services.deployment._run_docker_command", run_command)
    monkeypatch.setattr("app.services.deployment._container_exists", lambda _name: _async_false())
    monkeypatch.setattr("app.services.deployment.httpx.AsyncClient", lambda **_kwargs: Client())
    result = await run_deployment_pipeline(
        "conversation",
        user_id="user",
        target="api",
        token="",
        site_id="",
        progress=progress,
        deployment_id="a" * 32,
    )

    run = next(command for command in commands if command[:2] == ["docker", "run"])
    assert "--read-only" in run
    assert ["--cap-drop", "ALL"] == run[run.index("--cap-drop"):run.index("--cap-drop") + 2]
    assert ["--user", "65532:65532"] == run[run.index("--user"):run.index("--user") + 2]
    assert result.provider == "docker-runtime"
    assert result.url == "/published/" + "a" * 32 + "/"


async def _async_false():
    return False


@pytest.mark.asyncio
async def test_apk_build_mounts_only_current_workspace(tmp_path: Path, monkeypatch):
    (tmp_path / "gradlew").write_text("#!/bin/sh", encoding="utf-8")
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    commands = []

    class Process:
        returncode = 0
        async def communicate(self):
            apk = tmp_path / "app" / "build" / "outputs" / "apk" / "release" / "app.apk"
            apk.parent.mkdir(parents=True)
            apk.write_bytes(b"apk")
            return b"success", b""

    async def create_process(*command, **_kwargs):
        commands.append(command)
        return Process()

    async def progress(*_args):
        return None

    monkeypatch.setattr("app.services.deployment.asyncio.create_subprocess_exec", create_process)
    result = await _build_apk(tmp_path, progress)

    mount = commands[0][commands[0].index("--mount") + 1]
    assert mount == f"type=bind,src={tmp_path},dst=/workspace"
    assert result == b"apk"


@pytest.mark.asyncio
async def test_demo_apk_signing_generates_and_verifies_artifact(tmp_path: Path, monkeypatch):
    sdk = tmp_path / "sdk" / "build-tools" / "35.0.0"
    sdk.mkdir(parents=True)
    (sdk / "apksigner").write_text("tool", encoding="utf-8")
    monkeypatch.setenv("ANDROID_SDK_ROOT", str(tmp_path / "sdk"))
    monkeypatch.setattr(
        "app.services.deployment.FileStorageManager.get_absolute_path",
        lambda name: str(tmp_path / name),
    )
    actions = []

    async def command(args, _timeout, action, *_args):
        actions.append(action)
        if action == "生成演示签名":
            Path(args[args.index("-keystore") + 1]).touch()
        if action == "APK 签名":
            output = Path(args[args.index("--out") + 1])
            output.write_bytes(b"signed-apk")
        return "ok"

    async def progress(*_args):
        return None

    monkeypatch.setattr("app.services.deployment._run_trusted_command", command)
    result = await _sign_apk(
        b"unsigned-apk", "conversation", "user", {"signing_mode": "demo"}, progress
    )

    assert result == b"signed-apk"
    assert actions == ["生成演示签名", "APK 签名", "APK 签名校验"]


@pytest.mark.asyncio
async def test_cancelling_docker_command_terminates_child_process(monkeypatch):
    class Process:
        def __init__(self):
            self.returncode = None
            self.terminated = False
            self.done = asyncio.Event()

        async def communicate(self):
            await self.done.wait()
            return b"", b""

        def terminate(self):
            self.terminated = True
            self.returncode = -15
            self.done.set()

        async def wait(self):
            await self.done.wait()
            return self.returncode

    process = Process()

    async def create_process(*_args, **_kwargs):
        return process

    async def cancelled():
        return True

    monkeypatch.setattr("app.services.deployment.asyncio.create_subprocess_exec", create_process)

    with pytest.raises(DeploymentCancelled, match="用户取消"):
        await _run_docker_command(
            ["docker", "build", "."], 600, "API 镜像构建", cancelled
        )

    assert process.terminated is True
