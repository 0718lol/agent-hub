"""Shared project workspace resolution, local folder binding (workbench mode), and path validation."""
from __future__ import annotations

import re
from pathlib import Path

from app.core.runtime_mode import is_workbench_mode

_SAFE_CONVERSATION_ID = re.compile(r"^[A-Za-z0-9_.-]{1,320}$")
REPO_ROOT = Path(__file__).resolve().parents[3].resolve()
BACKEND_ROOT = Path(__file__).resolve().parents[2].resolve()
WORKSPACE_ROOT = (REPO_ROOT / "agenthub_export").resolve()


def is_safe_conversation_id(conversation_id: str) -> bool:
    """Return whether an identifier is safe to use as one directory name."""
    return bool(_SAFE_CONVERSATION_ID.fullmatch(conversation_id))


def _forbidden_roots() -> list[Path]:
    home = Path.home().resolve()
    roots = [
        BACKEND_ROOT,
        Path("/etc"),
        Path("/private/etc"),
        Path("/System"),
        Path("/usr"),
        Path("/bin"),
        Path("/sbin"),
        home / ".ssh",
        home / ".gnupg",
        home / ".aws",
        home / ".kube",
    ]
    resolved: list[Path] = []
    for root in roots:
        try:
            resolved.append(root.resolve())
        except OSError:
            continue
    return resolved


def validate_local_workspace_path(raw_path: str, *, create: bool = False) -> Path:
    """Validate a user-specified local project directory path safely."""
    cleaned = (raw_path or "").strip()
    if not cleaned:
        raise ValueError("本地工作目录路径不能为空")
    candidate = Path(cleaned).expanduser()
    if not candidate.is_absolute():
        raise ValueError("请填写绝对路径（或以 ~/ 开头的路径）")
    resolved = candidate.resolve()
    if resolved == resolved.anchor or str(resolved) == "/":
        raise ValueError("不能将系统根目录绑定为项目工作区")
    for forbidden in _forbidden_roots():
        if resolved == forbidden or resolved.is_relative_to(forbidden):
            raise ValueError(f"出于安全保护，不允许绑定敏感目录：{forbidden}")
    if resolved.exists():
        if not resolved.is_dir():
            raise ValueError("目标路径不是文件夹")
    elif create:
        if not resolved.parent.exists():
            raise ValueError(f"父目录不存在：{resolved.parent}")
        resolved.mkdir(parents=True, exist_ok=True)
    else:
        raise ValueError(f"目录不存在：{resolved}（可勾选自动创建）")
    return resolved


def is_managed_workspace(workspace_dir: Path | str) -> bool:
    """Return True if workspace_dir lives inside the managed agenthub_export root."""
    try:
        resolved = Path(workspace_dir).resolve()
        root = WORKSPACE_ROOT.resolve()
        return resolved != root and resolved.is_relative_to(root)
    except OSError:
        return False


def _bound_workspace_for_conversation(conversation_id: str) -> Path | None:
    if not is_workbench_mode():
        return None
    try:
        from sqlmodel import Session

        import app.core._engine as engine_mod
        from app.core.models import Conversation

        with Session(engine_mod.engine) as session:
            conv = session.get(Conversation, conversation_id)
            if conv and conv.workspace_path:
                return validate_local_workspace_path(conv.workspace_path, create=False)
    except Exception:
        return None
    return None


def resolve_workspace(conversation_id: str, *, create: bool = True) -> Path | None:
    """Return a conversation's bound local folder (in workbench mode) or managed sandbox workspace."""
    if not is_safe_conversation_id(conversation_id):
        return None

    bound = _bound_workspace_for_conversation(conversation_id)
    if bound is not None:
        return bound

    root = WORKSPACE_ROOT.resolve()
    if create:
        root.mkdir(parents=True, exist_ok=True)

    expected = root / conversation_id
    if expected.is_symlink():
        return None
    workspace = expected.resolve()
    if workspace != expected:
        return None

    if create:
        workspace.mkdir(parents=True, exist_ok=True)
    return workspace
