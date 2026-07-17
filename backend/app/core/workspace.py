"""Shared generated-project workspace resolution and legacy migration."""

import hashlib
import logging
import re
import shutil
import threading
from pathlib import Path

_SAFE_CONVERSATION_ID = re.compile(r"^[A-Za-z0-9_.-]{1,320}$")
WORKSPACE_ROOT = (Path(__file__).resolve().parents[3] / "agenthub_export").resolve()
LEGACY_WORKSPACE_ROOT = (Path(__file__).resolve().parents[2] / "data" / "sandbox").resolve()

logger = logging.getLogger("workspace")
_migration_lock = threading.Lock()


def is_safe_conversation_id(conversation_id: str) -> bool:
    """Return whether an identifier is safe to use as one directory name."""
    return bool(_SAFE_CONVERSATION_ID.fullmatch(conversation_id))


def _migration_marker(conversation_id: str) -> Path:
    digest = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()
    return WORKSPACE_ROOT / ".legacy-migrations" / digest


def _legacy_workspace(conversation_id: str) -> Path | None:
    legacy_root = (LEGACY_WORKSPACE_ROOT / conversation_id).resolve()
    if legacy_root.parent != LEGACY_WORKSPACE_ROOT or not legacy_root.is_dir():
        return None
    return legacy_root


def migrate_legacy_workspace(conversation_id: str, workspace: Path) -> int:
    """Copy a legacy sandbox into the unified workspace without overwriting files."""
    if not is_safe_conversation_id(conversation_id):
        return 0

    legacy_root = _legacy_workspace(conversation_id)
    if legacy_root is None:
        return 0

    marker = _migration_marker(conversation_id)
    if marker.exists():
        return 0

    copied = 0
    with _migration_lock:
        if marker.exists():
            return 0

        for source in legacy_root.rglob("*"):
            if source.is_symlink():
                continue

            relative = source.relative_to(legacy_root)
            target = workspace / relative
            resolved_target = target.resolve(strict=False)
            if resolved_target != workspace and workspace not in resolved_target.parents:
                logger.warning("Skipped unsafe legacy workspace path: %s", source)
                continue

            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif source.is_file() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                copied += 1

        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(copied), encoding="utf-8")

    if copied:
        logger.info("Migrated %s legacy files for conversation %s", copied, conversation_id)
    return copied


def resolve_workspace(
    conversation_id: str,
    *,
    create: bool = True,
    migrate_legacy: bool = True,
) -> Path | None:
    """Return a conversation workspace without allowing path traversal."""
    if not is_safe_conversation_id(conversation_id):
        return None

    workspace = (WORKSPACE_ROOT / conversation_id).resolve()
    if workspace.parent != WORKSPACE_ROOT:
        return None

    legacy_workspace = _legacy_workspace(conversation_id) if migrate_legacy else None
    if create or legacy_workspace is not None:
        WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
        workspace.mkdir(parents=True, exist_ok=True)
        if migrate_legacy:
            migrate_legacy_workspace(conversation_id, workspace)
    return workspace
