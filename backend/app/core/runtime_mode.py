"""Runtime mode resolution and boundary guards (`cloud` vs `workbench`).

AgentHub supports two orthogonal runtime profiles sharing one agent engine:
- `cloud` (default): Multi-tenant account authentication, isolated sandbox workspaces,
  and admin-only host capabilities. Local host directory mounting is disabled.
- `workbench`: Loopback-bound (`127.0.0.1`) personal workbench with zero-login local UX,
  real local project directory mounting, and live `personal-ai-os` (知序) dual-core bridge.
"""
from __future__ import annotations

from fastapi import HTTPException

from app.core.config import settings


def is_workbench_mode() -> bool:
    """Return True when the local Personal Workbench runtime profile is active."""
    mode_val = str(getattr(settings, "mode", "cloud") or "cloud").strip().lower()
    return bool(getattr(settings, "workbench_mode", False) or mode_val == "workbench")


def is_passwordless_workbench() -> bool:
    """Return True when running in local workbench mode without an API secret."""
    return bool(is_workbench_mode() and not settings.api_secret)


def require_workbench_mode() -> None:
    """Guard endpoints that mount host directories or bridge to local Personal AI OS."""
    if not is_workbench_mode():
        raise HTTPException(
            status_code=403,
            detail="当前处于云端多租户模式（cloud），本机目录挂载与本地知序桥接已关闭；本地使用请以 ./start.sh 或 AGENTHUB_MODE=workbench 启动",
        )
