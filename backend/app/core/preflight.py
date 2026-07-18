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
from app.core.file_storage import UPLOAD_DIR, FileStorageManager
from app.core.redis import redis_manager
from app.core.workspace import WORKSPACE_ROOT
from app.services.deployment_queue import WORKER_HEARTBEAT_KEY
from app.services.generation_queue import (
    WORKER_HEARTBEAT_KEY as GENERATION_WORKER_HEARTBEAT_KEY,
)

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
    required_tables = {
        "conversations", "messages", "tenant_configs", "knowledge_bases", "alembic_version"
    }
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


async def _redis_checks(
    deployment_required: bool,
    generation_required: bool,
) -> list[PreflightCheck]:
    try:
        if not await redis_manager.check_connection():
            raise RuntimeError("Redis ping failed")
        client = redis_manager.get_client()
        deployment_worker = await client.get(WORKER_HEARTBEAT_KEY)
        generation_worker = await client.get(GENERATION_WORKER_HEARTBEAT_KEY)
    except Exception as exc:
        redis_required = deployment_required or generation_required
        redis_status = "fail" if redis_required else "warn"
        return [
            PreflightCheck(
                "redis", "Redis", redis_status, str(exc)[:240],
                required=redis_required,
            ),
            PreflightCheck(
                "deployment_worker",
                "构建 Worker",
                "fail" if deployment_required else "warn",
                "Redis 不可用，无法读取 Worker 心跳",
                required=deployment_required,
            ),
            PreflightCheck(
                "generation_worker",
                "生成 Worker",
                "fail" if generation_required else "warn",
                "Redis 不可用，无法读取 Worker 心跳",
                required=generation_required,
            ),
        ]
    return [
        PreflightCheck(
            "redis",
            "Redis",
            "pass",
            "队列连接正常",
            required=deployment_required or generation_required,
        ),
        PreflightCheck(
            "deployment_worker",
            "构建 Worker",
            "pass" if deployment_worker else ("fail" if deployment_required else "warn"),
            f"在线：{deployment_worker}"
            if deployment_worker else "未检测到 15 秒内的 Worker 心跳",
            required=deployment_required,
        ),
        PreflightCheck(
            "generation_worker",
            "生成 Worker",
            "pass" if generation_worker else ("fail" if generation_required else "warn"),
            f"在线：{generation_worker}"
            if generation_worker else "未检测到 15 秒内的 Worker 心跳",
            required=generation_required,
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
    if settings.auth_mode == "proxy":
        proxy_ok = len(settings.trusted_proxy_secret) >= 32
        checks.append(PreflightCheck(
            "identity_provider",
            "统一身份认证",
            "pass" if proxy_ok else ("fail" if production else "warn"),
            "已启用受信任身份代理" if proxy_ok else "TRUSTED_PROXY_SECRET 未配置或过短",
            required=production,
        ))
    else:
        checks.append(PreflightCheck(
            "identity_provider",
            "统一身份认证",
            "warn",
            "使用共享密钥演示模式；外部多人使用建议设置 AGENTHUB_AUTH_MODE=proxy",
        ))
    checks.append(PreflightCheck(
        "api_client_tokens",
        "API 客户端独立凭证",
        "pass" if settings.api_client_tokens_json else "warn",
        "已配置客户端独立 Token" if settings.api_client_tokens_json
        else "未配置时 Bearer 客户端仍共用 API Secret",
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
    storage_ok, storage_detail = FileStorageManager.healthcheck()
    if settings.storage_backend == "local" and production:
        storage_status = "warn"
        storage_detail += "；多主机部署建议改用 S3/MinIO"
    else:
        storage_status = "pass" if storage_ok else ("fail" if production else "warn")
    checks.append(PreflightCheck(
        "object_storage",
        "共享文件存储",
        storage_status,
        storage_detail,
        required=production and settings.storage_backend == "s3",
    ))
    checks.append(PreflightCheck(
        "vector_storage",
        "共享向量库",
        "pass" if settings.chroma_host else "warn",
        f"Chroma 服务：{settings.chroma_host}:{settings.chroma_port}"
        if settings.chroma_host else "使用本地 Chroma；多主机部署请配置 AGENTHUB_CHROMA_HOST",
    ))
    return checks


async def run_preflight(profile: PreflightProfile = "core") -> dict:
    deployment_required = profile in {"deployment", "production"}
    generation_required = (
        profile == "production" or settings.generation_worker_enabled
    )
    checks = await asyncio.to_thread(_database_checks)
    checks.extend([
        await asyncio.to_thread(
            _writable_check, "workspace", "生成项目目录", WORKSPACE_ROOT
        ),
        await asyncio.to_thread(
            _writable_check, "uploads", "构建产物目录", Path(UPLOAD_DIR)
        ),
    ])
    checks.extend(await _redis_checks(deployment_required, generation_required))
    checks.append(await _docker_check())
    checks.extend(await asyncio.to_thread(_configuration_checks, profile))
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
