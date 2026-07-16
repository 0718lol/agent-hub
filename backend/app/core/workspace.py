"""Shared generated-project workspace resolution and validation."""

import re
from pathlib import Path

_SAFE_CONVERSATION_ID = re.compile(r"^[A-Za-z0-9_.-]{1,320}$")
WORKSPACE_ROOT = (Path(__file__).resolve().parents[3] / "agenthub_export").resolve()


def is_safe_conversation_id(conversation_id: str) -> bool:
    """Return whether an identifier is safe to use as one directory name."""
    return bool(_SAFE_CONVERSATION_ID.fullmatch(conversation_id))


def resolve_workspace(conversation_id: str, *, create: bool = True) -> Path | None:
    """Return a conversation workspace without allowing path traversal."""
    if not is_safe_conversation_id(conversation_id):
        return None

    if create:
        WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

    workspace = (WORKSPACE_ROOT / conversation_id).resolve()
    if workspace.parent != WORKSPACE_ROOT:
        return None

    if create:
        workspace.mkdir(parents=True, exist_ok=True)
    return workspace
