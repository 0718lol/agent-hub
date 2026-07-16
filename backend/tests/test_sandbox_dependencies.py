"""Dependency policy and cache-plan tests."""

import json

import pytest

from app.core.sandbox_dependencies import DependencyPolicyError, resolve_dependencies


def _write_package(tmp_path, dependencies):
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "demo", "dependencies": dependencies}),
        encoding="utf-8",
    )


def test_node_manifest_builds_a_cached_install_plan(tmp_path):
    _write_package(tmp_path, {"react": "^18.3.1"})

    resolution = resolve_dependencies(tmp_path, "npm run build")

    assert len(resolution.plans) == 1
    plan = resolution.plans[0]
    assert plan.ecosystem == "node"
    assert plan.volume_name.startswith("agenthub-sandbox-node-")
    assert "--ignore-scripts" in plan.install_script
    assert "node_modules" in plan.runtime_bootstrap


def test_node_install_command_is_handled_by_dependency_stage(tmp_path):
    _write_package(tmp_path, {"vite": "5.4.0"})

    assert resolve_dependencies(tmp_path, "npm install --no-fund").install_only


def test_node_manifest_rejects_external_dependency_url(tmp_path):
    _write_package(tmp_path, {"demo": "https://evil.example/demo.tgz"})

    with pytest.raises(DependencyPolicyError, match="npm"):
        resolve_dependencies(tmp_path, "npm test")


def test_python_requirements_must_be_pinned(tmp_path):
    (tmp_path / "requirements.txt").write_text("fastapi>=0.115\n", encoding="utf-8")

    with pytest.raises(DependencyPolicyError, match="name==version"):
        resolve_dependencies(tmp_path, "pytest -q")


def test_python_requirements_build_a_binary_only_plan(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "fastapi==0.115.0\nuvicorn==0.30.6\n",
        encoding="utf-8",
    )

    resolution = resolve_dependencies(tmp_path, "pytest -q")

    plan = resolution.plans[0]
    assert plan.ecosystem == "python"
    assert "--only-binary=:all:" in plan.install_script
    assert plan.mount(readonly=True).endswith(",readonly")
