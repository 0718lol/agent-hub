"""Structured project parsing, materialization, and tenant API tests."""

import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.adapters.tool_converter import get_project_tools
from app.core import workspace as workspace_module
from app.core.tenancy import scope_conversation_id
from app.routers import projects as projects_router
from app.services import project_workspace
from app.services.project_workspace import GeneratedProjectFile, materialize_project_files, parse_generated_files
from app.tools.registry import TOOL_REGISTRY, AgentTool, ToolResult


class _ExampleTool(AgentTool):
    name = "example_project_tool"
    description = "example"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True)


def test_external_adapter_reads_the_real_tool_registry(monkeypatch):
    monkeypatch.setitem(TOOL_REGISTRY, _ExampleTool.name, _ExampleTool())

    tools = get_project_tools([_ExampleTool.name])

    assert tools == [{
        "name": _ExampleTool.name,
        "description": "example",
        "parameters": {"type": "object", "properties": {}},
    }]


def test_parse_generated_files_supports_paths_and_legacy_fences():
    output = """
文件: src/App.jsx
```jsx
export default function App() { return <main /> }
```
```css path=src/styles.css
main { color: red; }
```
```python
print('legacy')
```
"""

    files = parse_generated_files(output, "agent_frontend")

    assert [item.path for item in files] == ["src/App.jsx", "src/styles.css", "main.py"]
    assert [item.language for item in files] == ["jsx", "css", "python"]


def test_parse_generated_files_never_writes_a_traversal_path():
    files = parse_generated_files("```python path=../../outside.py\nprint('safe')\n```", "agent_backend")

    assert files[0].path == "main.py"


@pytest.mark.asyncio
async def test_materialization_merges_concurrent_agent_files(tmp_path, monkeypatch):
    workspace_root = tmp_path / "agenthub_export"
    monkeypatch.setattr(workspace_module, "WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(workspace_module, "LEGACY_WORKSPACE_ROOT", tmp_path / "legacy")

    snapshot_count = {"value": 0}

    async def fake_checkpoint(_workspace, _message):
        snapshot_count["value"] += 1
        return f"snapshot-{snapshot_count['value']}"

    monkeypatch.setattr(project_workspace, "git_checkpoint", fake_checkpoint)
    await asyncio.gather(
        materialize_project_files(
            "conversation",
            "agent_frontend",
            [GeneratedProjectFile("src/App.jsx", "jsx", "export default 1")],
        ),
        materialize_project_files(
            "conversation",
            "agent_backend",
            [GeneratedProjectFile("main.py", "python", "print('api')")],
        ),
    )

    workspace = workspace_root / "conversation"
    manifest = project_workspace._load_manifest(workspace)
    assert (workspace / "src" / "App.jsx").is_file()
    assert (workspace / "main.py").is_file()
    assert [item["path"] for item in manifest["files"]] == ["main.py", "src/App.jsx"]
    assert snapshot_count["value"] == 2


@pytest.mark.asyncio
async def test_project_api_reads_only_the_current_tenant(tmp_path, monkeypatch):
    workspace_root = tmp_path / "agenthub_export"
    monkeypatch.setattr(workspace_module, "WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(workspace_module, "LEGACY_WORKSPACE_ROOT", tmp_path / "legacy")
    monkeypatch.setattr(projects_router, "request_user_id", lambda _request: "user-A")

    async def fake_checkpoint(_workspace, _message):
        return "snapshot-a"

    async def fake_git_log(_workspace):
        return []

    monkeypatch.setattr(project_workspace, "git_checkpoint", fake_checkpoint)
    monkeypatch.setattr(project_workspace, "git_log", fake_git_log)
    await materialize_project_files(
        scope_conversation_id("user-A", "shared"),
        "agent_frontend",
        [GeneratedProjectFile("index.html", "html", "<h1>own</h1>")],
    )
    await materialize_project_files(
        scope_conversation_id("user-B", "shared"),
        "agent_frontend",
        [GeneratedProjectFile("secret.html", "html", "<h1>private</h1>")],
    )

    app = FastAPI()
    app.include_router(projects_router.router, prefix="/api")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        summary_response = await client.get("/api/projects/shared")
        file_response = await client.get("/api/projects/shared/files?path=index.html")
        secret_response = await client.get("/api/projects/shared/files?path=secret.html")

    assert summary_response.status_code == 200
    assert [item["path"] for item in summary_response.json()["files"]] == ["index.html"]
    assert file_response.json()["content"] == "<h1>own</h1>"
    assert secret_response.status_code == 404
