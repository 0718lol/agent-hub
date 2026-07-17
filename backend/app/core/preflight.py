"""Deployment readiness checks shared by the API and command-line preflight."""

import asyncio
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import inspect, text

from app.core._engine import engine
from app.core.config import settings
from app.core.file_storage import UPLOAD_DIR
from app.core.redis import redis_manager
from app.core.workspace import WORKSPACE_ROOT
from app.services.deployment_queue import WORKER_HEARTBEAT_KEY

PreflightProfile = Literal["core", "deployment", "production"]


@dataclass(frozen=True)
class PreflightCheck:
    key: str
    label: str
    status: Literal["pass", "warn", "fail"]
    detail: str
    required: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _database_checks() -> list[PreflightCheck]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        tables = set(inspect(engine).get_table_names())
    except Exception as exc:
        return [PreflightCheck(
            "database", "数据库连接", "fail", str(exc)[:240], required=True,
        )]
    required_tables = {"conversations", "messages", "tenant_configs", "alembic_version"}
    missing = sorted(required_tables - tables)
    return [
        PreflightCheck("database", "数据库连接", "pass", "连接正常", required=True),
        PreflightCheck(
            "database_schema",
            "数据库迁移",
            "fail" if missing else "pass",
            f"缺少表：{', '.join(missing)}" if missing else "Schema 与 Alembic 版本表完整",
            required=True,
        ),
    ]


def _writable_check(key: str, label: str, directory: Path) -> PreflightCheck:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, path = tempfile.mkstemp(prefix=".agenthub-preflight-", dir=directory)
        os.close(descriptor)
        Path(path).unlink(missing_ok=True)
        return PreflightCheck(key, label, "pass", str(directory), required=True)
    except OSError as exc:
        return PreflightCheck(key, label, "fail", str(exc)[:240], required=True)


async def _redis_checks(required: bool) -> list[PreflightCheck]:
    try:
        if not await redis_manager.check_connection():
            raise RuntimeError("Redis ping failed")
        client = redis_manager.get_client()
        worker = await client.get(WORKER_HEARTBEAT_KEY)
    except Exception as exc:
        status = "fail" if required else "warn"
        return [
            PreflightCheck("redis", "Redis", status, str(exc)[:240], required=required),
            PreflightCheck(
                "deployment_worker", "构建 Worker", status,
                "Redis 不可用，无法读取 Worker 心跳", required=required,
            ),
        ]
    return [
        PreflightCheck("redis", "Redis", "pass", "队列连接正常", required=required),
        PreflightCheck(
            "deployment_worker",
            "构建 Worker",
            "pass" if worker else ("fail" if required else "warn"),
            f"在线：{worker}" if worker else "未检测到 15 秒内的 Worker 心跳",
            required=required,
        ),
    ]


async def _docker_check() -> PreflightCheck:
    try:
        process = await asyncio.create_subprocess_exec(
            "docker", "info",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=4)
        if process.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="replace")[-240:])
        return PreflightCheck(
            "local_docker", "本地 Docker", "pass",
            "本节点可启动隔离 Web 预览；远程构建仍由 Worker 执行",
        )
    except Exception as exc:
        return PreflightCheck(
            "local_docker", "本地 Docker", "warn",
            f"本节点不能启动 Vite 容器：{str(exc)[:200]}",
        )


def _configuration_checks(profile: PreflightProfile) -> list[PreflightCheck]:
    production = profile == "production"
    checks = []
    api_secret_ok = len(settings.api_secret) >= 32
    checks.append(PreflightCheck(
        "api_secret", "API 鉴权密钥",
        "pass" if api_secret_ok else ("fail" if production else "warn"),
        "已配置" if api_secret_ok else "AGENTHUB_API_SECRET 未配置或少于 32 字符",
        required=production,
    ))
    encryption_ok = bool(os.environ.get("AGENTHUB_ENCRYPT_KEY", ""))
    checks.append(PreflightCheck(
        "encryption_key", "配置加密密钥",
        "pass" if encryption_ok else ("fail" if production else "warn"),
        "已配置" if encryption_ok else "AGENTHUB_ENCRYPT_KEY 未配置，将使用机器派生密钥",
        required=production,
    ))
    public_url_ok = settings.public_base_url.startswith(("https://", "http://localhost"))
    checks.append(PreflightCheck(
        "public_base_url", "公网地址",
        "pass" if public_url_ok else ("fail" if production else "warn"),
        settings.public_base_url or "AGENTHUB_PUBLIC_BASE_URL 未配置",
        required=production,
    ))
    netlify_ok = bool(settings.netlify_token and settings.netlify_site_id)
    checks.append(PreflightCheck(
        "netlify", "Web 公网发布", "pass" if netlify_ok else "warn",
        "Netlify 凭证已配置" if netlify_ok else "未配置 Netlify，将只生成 Web ZIP",
    ))
    return checks


async def run_preflight(profile: PreflightProfile = "core") -> dict:
    deployment_required = profile in {"deployment", "production"}
    checks = await asyncio.to_thread(_database_checks)
    checks.extend([
        await asyncio.to_thread(
            _writable_check, "workspace", "生成项目目录", WORKSPACE_ROOT
        ),
        await asyncio.to_thread(
            _writable_check, "uploads", "构建产物目录", Path(UPLOAD_DIR)
        ),
    ])
    checks.extend(await _redis_checks(deployment_required))
    checks.append(await _docker_check())
    checks.extend(_configuration_checks(profile))
    required_failures = [check for check in checks if check.required and check.status == "fail"]
    return {
        "profile": profile,
        "ready": not required_failures,
        "summary": {
            "pass": sum(check.status == "pass" for check in checks),
            "warn": sum(check.status == "warn" for check in checks),
            "fail": sum(check.status == "fail" for check in checks),
        },
        "checks": [check.to_dict() for check in checks],
    }
