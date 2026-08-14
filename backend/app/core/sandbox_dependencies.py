"""Validated dependency plans for generated-project sandboxes."""

import hashlib
import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import settings

SANDBOX_WORKSPACE_PATH = "/tmp/agenthub-workspace"  # nosec B108


class DependencyPolicyError(ValueError):
    """A generated dependency manifest violates the sandbox policy."""


@dataclass(frozen=True)
class DependencyPlan:
    ecosystem: str
    digest: str
    volume_name: str
    target: str
    install_script: str
    install_environment: tuple[tuple[str, str], ...]
    runtime_environment: tuple[tuple[str, str], ...]
    runtime_bootstrap: str

    def mount(self, *, readonly: bool) -> str:
        suffix = ",readonly" if readonly else ""
        return f"type=volume,src={self.volume_name},dst={self.target}{suffix}"


@dataclass(frozen=True)
class DependencyResolution:
    plans: tuple[DependencyPlan, ...]
    install_only: bool = False


_NODE_COMMAND = re.compile(r"(?:^|[;&|]\s*|\s)(?:npm|npx|node|pnpm|yarn|vite|tsc)\b", re.I)
_PYTHON_COMMAND = re.compile(r"(?:^|[;&|]\s*|\s)(?:python3?|pytest|pip3?|uvicorn|fastapi)\b", re.I)
_PINNED_REQUIREMENT = re.compile(
    r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_.,-]+\])?==[A-Za-z0-9_.+!-]+$"
)


def _read_bounded(path: Path, limit: int = 2 * 1024 * 1024) -> bytes:
    try:
        if path.stat().st_size > limit:
            raise DependencyPolicyError(f"依赖清单过大: {path.name}")
        return path.read_bytes()
    except OSError as exc:
        raise DependencyPolicyError(f"无法读取依赖清单: {path.name}") from exc


def _load_json(path: Path) -> tuple[dict, bytes]:
    raw = _read_bounded(path)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise DependencyPolicyError(f"{path.name} 不是有效的 UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise DependencyPolicyError(f"{path.name} 顶层必须是对象")
    return data, raw


def _validate_package_manifest(package: dict) -> None:
    forbidden_fields = {"bundledDependencies", "bundleDependencies", "overrides", "resolutions", "workspaces"}
    present_forbidden = sorted(forbidden_fields.intersection(package))
    if present_forbidden:
        raise DependencyPolicyError(
            "package.json 包含不允许的依赖控制字段: " + ", ".join(present_forbidden)
        )

    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        dependencies = package.get(section, {})
        if dependencies is None:
            continue
        if not isinstance(dependencies, dict):
            raise DependencyPolicyError(f"package.json 的 {section} 必须是对象")
        for name, specifier in dependencies.items():
            if not isinstance(name, str) or not isinstance(specifier, str):
                raise DependencyPolicyError("package.json 包名和版本必须是字符串")
            lowered = specifier.strip().lower()
            if (
                not lowered
                or "://" in lowered
                or lowered.startswith(("git", "file:", "link:", "workspace:", "npm:"))
            ):
                raise DependencyPolicyError(f"不允许的 npm 依赖来源: {name}={specifier}")


def _validate_package_lock(lock: dict) -> None:
    registry = urlparse(settings.runtime_npm_registry)
    if registry.scheme != "https" or not registry.hostname:
        raise DependencyPolicyError("npm Registry 必须是 HTTPS 地址")

    if not isinstance(lock.get("lockfileVersion"), int) or lock["lockfileVersion"] < 2:
        raise DependencyPolicyError("package-lock.json 必须使用 lockfileVersion 2 或更高版本")
    packages = lock.get("packages")
    if not isinstance(packages, dict):
        raise DependencyPolicyError("package-lock.json 缺少 packages 对象")
    for metadata in packages.values():
        if not isinstance(metadata, dict):
            continue
        resolved = metadata.get("resolved")
        if not resolved:
            continue
        parsed = urlparse(str(resolved))
        if parsed.scheme != "https" or parsed.hostname != registry.hostname:
            raise DependencyPolicyError(f"锁文件包含未授权 npm 来源: {resolved}")
        if not metadata.get("integrity"):
            raise DependencyPolicyError(f"锁文件依赖缺少完整性校验: {resolved}")


def _node_plan(workspace: Path) -> DependencyPlan:
    package, package_raw = _load_json(workspace / "package.json")
    _validate_package_manifest(package)

    lock_path = workspace / "package-lock.json"
    lock_raw = b""
    install = "npm install --ignore-scripts --no-audit --no-fund"
    if lock_path.is_file():
        lock, lock_raw = _load_json(lock_path)
        _validate_package_lock(lock)
        install = "npm ci --ignore-scripts --no-audit --no-fund"

    digest = hashlib.sha256(
        b"node-v1\0" + settings.runtime_sandbox_image.encode() + b"\0" + package_raw + b"\0" + lock_raw
    ).hexdigest()
    copy_lock = (
        f"cp {SANDBOX_WORKSPACE_PATH}/package-lock.json /deps/node/package-lock.json && "
        if lock_raw else ""
    )
    script = (
        "set -eu; rm -rf /deps/node/*; "
        f"cp {SANDBOX_WORKSPACE_PATH}/package.json /deps/node/package.json; "
        f"{copy_lock}"
        f"cd /deps/node; {install}; touch /deps/node/.agenthub-ready"
    )
    return DependencyPlan(
        ecosystem="node",
        digest=digest,
        volume_name=f"agenthub-sandbox-node-{digest[:24]}",
        target="/deps/node",
        install_script=script,
        install_environment=(("NPM_CONFIG_REGISTRY", settings.runtime_npm_registry),),
        runtime_environment=(("NODE_PATH", "/deps/node/node_modules"),),
        runtime_bootstrap=f"ln -s /deps/node/node_modules {SANDBOX_WORKSPACE_PATH}/node_modules",
    )


def _python_plan(workspace: Path) -> DependencyPlan:
    requirements_path = workspace / "requirements.txt"
    raw = _read_bounded(requirements_path)
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise DependencyPolicyError("requirements.txt 必须使用 UTF-8") from exc

    requirements = []
    for line in lines:
        value = line.split("#", 1)[0].strip()
        if not value:
            continue
        if not _PINNED_REQUIREMENT.fullmatch(value):
            raise DependencyPolicyError(f"Python 依赖必须固定为 name==version: {value}")
        requirements.append(value)
    if not requirements:
        raise DependencyPolicyError("requirements.txt 没有可安装的固定版本依赖")

    digest = hashlib.sha256(
        b"python-v1\0" + settings.runtime_sandbox_image.encode() + b"\0" + raw
    ).hexdigest()
    script = (
        "set -eu; rm -rf /deps/python/*; "
        "python -m venv /deps/python/venv; "
        "/deps/python/venv/bin/pip install --disable-pip-version-check --no-input "
        f"--only-binary=:all: -r {SANDBOX_WORKSPACE_PATH}/requirements.txt; "
        "touch /deps/python/.agenthub-ready"
    )
    return DependencyPlan(
        ecosystem="python",
        digest=digest,
        volume_name=f"agenthub-sandbox-python-{digest[:24]}",
        target="/deps/python",
        install_script=script,
        install_environment=(("PIP_INDEX_URL", settings.runtime_pypi_index_url),),
        runtime_environment=(("VIRTUAL_ENV", "/deps/python/venv"),),
        runtime_bootstrap="",
    )


def _install_only(command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens:
        return False
    if tokens[:2] in (["npm", "ci"], ["npm", "install"]):
        return all(token.startswith("-") for token in tokens[2:])
    prefixes = (["pip", "install"], ["pip3", "install"], ["python", "-m", "pip", "install"])
    return any(tokens[:len(prefix)] == list(prefix) and "-r" in tokens for prefix in prefixes)


def resolve_dependencies(workspace: Path, command: str) -> DependencyResolution:
    """Return dependency caches required by a shell command."""
    plans: list[DependencyPlan] = []
    if _NODE_COMMAND.search(command) and (workspace / "package.json").is_file():
        plans.append(_node_plan(workspace))
    if _PYTHON_COMMAND.search(command) and (workspace / "requirements.txt").is_file():
        plans.append(_python_plan(workspace))
    return DependencyResolution(tuple(plans), install_only=bool(plans) and _install_only(command))
