"""
Shared utilities for CRUD sub-modules.

Provides JSON parsing helpers and the global write-lock decorator used
by every database write operation.
"""
import functools
import json
import threading

# ============================================================
# Helpers
# ============================================================

_MAX_JSON_PARSE_SIZE = 1_000_000  # 1MB -- skip parsing for oversized payloads


def _safe_json_loads(s):
    """Parse JSON with size guard and graceful fallback."""
    if isinstance(s, str) and len(s) > _MAX_JSON_PARSE_SIZE:
        return {"text": s, "_warning": "payload_too_large_skipped"}
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return {"text": s}


# Global reentrant write lock to serialize all SQLite database writes
_db_write_lock = threading.RLock()


def db_write_transaction(func):
    """
    Decorator to serialize all SQLite database write operations across
    threads/coroutines, ensuring thread-safety and zero database locked
    conflicts.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with _db_write_lock:
            return func(*args, **kwargs)
    return wrapper
