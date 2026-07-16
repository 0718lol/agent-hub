"""Real Docker smoke tests for the runtime sandbox image."""

import json
import os

import pytest

from app.core.sandbox_dependencies import resolve_dependencies
from app.core.sandbox_manager import DockerSandbox

pytestmark = pytest.mark.skipif(
    os.environ.get("AGENTHUB_DOCKER_INTEGRATION") != "1",
    reason="requires the real AgentHub Docker sandbox image",
)


@pytest.mark.asyncio
async def test_runtime_image_executes_python_and_cached_node_workspace(tmp_path):
    sandbox = DockerSandbox()
    python_result = await sandbox.execute(
        "import pandas; print('python-ready')",
        "python",
        timeout=30,
    )
    assert python_result["status"] == "success", python_result["stderr"]
    assert "python-ready" in python_result["stdout"]

    (tmp_path / "package.json").write_text(
        json.dumps({
            "name": "sandbox-smoke",
            "version": "1.0.0",
            "scripts": {"check": "node -e \"console.log('node-ready')\""},
        }),
        encoding="utf-8",
    )
    plan = resolve_dependencies(tmp_path, "npm install").plans[0]
    try:
        install_result = await sandbox.execute("npm install", "shell", 120, workspace=tmp_path)
        assert install_result["status"] == "success", install_result["stderr"]

        run_result = await sandbox.execute("npm run check", "shell", 60, workspace=tmp_path)
        assert run_result["status"] == "success", run_result["stderr"]
        assert "node-ready" in run_result["stdout"]
    finally:
        await sandbox._run_cli(["volume", "rm", "-f", plan.volume_name])
