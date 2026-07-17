"""Structured generated-project parsing, materialization, and inspection."""

import asyncio
import hashlib
import json
import os
import re
import shlex
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from app.core.git_sandbox import git_checkpoint, git_log, git_rollback_to, run_git_cmd
from app.core.redis import redis_manager
from app.core.workspace import resolve_workspace

MANIFEST_DIRECTORY = ".agenthub"
MANIFEST_PATH = f"{MANIFEST_DIRECTORY}/project.json"
IGNORED_TREE_DIRECTORIES = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", MANIFEST_DIRECTORY,
}
MAX_PROJECT_FILES = 2_000
MAX_FILE_READ_BYTES = 1_000_000

_workspace_locks: dict[str, asyncio.Lock] = {}

_FENCE_PATTERN = re.compile(r"```([^\r\n`]*)\r?\n(.*?)```", re.DOTALL)
_PATH_LABEL_PATTERN = re.compile(
    r"(?:文件|文件名|路径|file|filename|path)\s*[:：]\s*[`\"']?([^`\"'\s]+)[`\"']?\s*$",
    re.IGNORECASE,
)
_LANGUAGE_ALIASES = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "htm": "html",
    "yml": "yaml",
    "kt": "kotlin",
}


@dataclass(frozen=True)
class GeneratedProjectFile:
    path: str
    language: str
    code: str


def _local_workspace_lock(workspace: Path) -> asyncio.Lock:
    key = str(workspace)
    lock = _workspace_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _workspace_locks[key] = lock
    return lock


@asynccontextmanager
async def _workspace_lock(workspace: Path):
    """Serialize writes locally and across backend replicas when Redis is online."""
    local_lock = _local_workspace_lock(workspace)
    async with local_lock:
        redis_key = "agenthub:workspace-lock:" + hashlib.sha256(
            str(workspace).encode("utf-8")
        ).hexdigest()
        token = uuid.uuid4().hex
        redis_client = None
        acquired = False
        if await redis_manager.check_connection():
            redis_client = redis_manager.get_client()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                acquired = bool(await redis_client.set(redis_key, token, nx=True, ex=180))
                if acquired:
                    break
                await asyncio.sleep(0.1)
            if not acquired:
                raise TimeoutError("Timed out waiting for the project workspace lock")
        try:
            yield
        finally:
            if redis_client is not None and acquired:
                try:
                    await redis_client.eval(
                        "if redis.call('get', KEYS[1]) == ARGV[1] then "
                        "return redis.call('del', KEYS[1]) else return 0 end",
                        1,
                        redis_key,
                        token,
                    )
                except Exception:
                    pass


def _normalize_language(language: str) -> str:
    normalized = language.strip().lower() or "text"
    return _LANGUAGE_ALIASES.get(normalized, normalized)


def _safe_relative_path(path: str) -> str | None:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized or len(normalized) > 240 or "\x00" in normalized:
        return None
    candidate = PurePosixPath(normalized)
    if candidate.is_absolute() or any(part in ("", ".", "..") for part in candidate.parts):
        return None
    if candidate.parts[0] in (".git", MANIFEST_DIRECTORY):
        return None
    return candidate.as_posix()


def _language_from_path(path: str) -> str:
    name = PurePosixPath(path).name.lower()
    if name == "dockerfile":
        return "dockerfile"
    extension = PurePosixPath(path).suffix.lower().lstrip(".")
    return _normalize_language(extension or "text")


def _parse_fence_info(info: str) -> tuple[str, str | None]:
    raw = info.strip()
    if not raw:
        return "html", None

    try:
        tokens = shlex.split(raw)
    except ValueError:
        tokens = raw.split()

    language = ""
    path_hint = None
    first = tokens[0] if tokens else ""
    if ":" in first and not first.startswith(("path=", "file=", "filename=")):
        possible_language, possible_path = first.split(":", 1)
        if possible_path:
            language = possible_language
            path_hint = possible_path
    elif first.startswith(("path=", "file=", "filename=")):
        path_hint = first.split("=", 1)[1]
    elif "/" in first or PurePosixPath(first).suffix:
        path_hint = first
    else:
        language = first

    for token in tokens[1:]:
        if token.startswith(("path=", "file=", "filename=")):
            path_hint = token.split("=", 1)[1]
            break
        if path_hint is None and ("/" in token or PurePosixPath(token).suffix):
            path_hint = token

    if path_hint and not language:
        language = _language_from_path(path_hint)
    return _normalize_language(language or "text"), path_hint


def _preceding_path(text: str, fence_start: int) -> str | None:
    prefix = text[max(0, fence_start - 240):fence_start].rstrip()
    if not prefix:
        return None
    last_line = prefix.splitlines()[-1].strip()
    match = _PATH_LABEL_PATTERN.search(last_line)
    return match.group(1) if match else None


def _default_path(language: str, code: str, agent_id: str) -> str:
    if language == "html":
        return "index.html"
    if language == "css":
        return "styles.css"
    if language == "javascript":
        return "src/app.js"
    if language == "jsx":
        return "src/App.jsx"
    if language == "typescript":
        return "src/index.ts"
    if language == "tsx":
        return "src/App.tsx"
    if language == "python":
        return "tests/test_generated.py" if agent_id == "agent_tester" else "main.py"
    if language == "sql":
        return "schema.sql"
    if language == "json":
        return "package.json" if '"scripts"' in code or '"dependencies"' in code else "data.json"
    if language == "yaml":
        return "docker-compose.yml" if "services:" in code else "config.yml"
    if language == "dockerfile":
        return "Dockerfile"
    if language in ("bash", "shell", "sh"):
        return "scripts/setup.sh"
    if language == "kotlin":
        return "app/src/main/java/com/agenthub/app/MainActivity.kt"
    if language == "java":
        return "src/main/java/com/agenthub/app/Main.java"
    if language == "xml":
        return "app/src/main/AndroidManifest.xml" if "<manifest" in code else "layout.xml"
    return f"generated.{language or 'txt'}"


def _deduplicate_path(path: str, used_paths: set[str]) -> str:
    if path not in used_paths:
        return path
    candidate = PurePosixPath(path)
    suffix = "".join(candidate.suffixes)
    stem = candidate.name[:-len(suffix)] if suffix else candidate.name
    parent = candidate.parent
    index = 2
    while True:
        name = f"{stem}-{index}{suffix}"
        deduplicated = (parent / name).as_posix()
        if deduplicated not in used_paths:
            return deduplicated
        index += 1


def parse_generated_files(text: str, agent_id: str) -> list[GeneratedProjectFile]:
    """Parse path-aware Markdown fences while remaining compatible with legacy output."""
    files = []
    used_paths: set[str] = set()
    for match in _FENCE_PATTERN.finditer(text or ""):
        language, info_path = _parse_fence_info(match.group(1))
        path = _safe_relative_path(info_path or _preceding_path(text, match.start()) or "")
        if path is None:
            path = _default_path(language, match.group(2), agent_id)
        path = _deduplicate_path(path, used_paths)
        used_paths.add(path)
        files.append(GeneratedProjectFile(
            path=path,
            language=language,
            code=match.group(2).strip(),
        ))

    if not files:
        html_match = re.search(
            r"(<!DOCTYPE[\s\S]*?</html>|<html[\s\S]*?</html>|<body[\s\S]*?</body>)",
            text or "",
            re.IGNORECASE,
        )
        if html_match:
            files.append(GeneratedProjectFile("index.html", "html", html_match.group(1).strip()))
    return files


def _detect_project_type(paths: set[str]) -> str:
    names = {PurePosixPath(path).name for path in paths}
    if "gradlew" in names and ("build.gradle" in names or "build.gradle.kts" in names):
        return "apk"
    if "project.config.json" in names and "app.json" in names:
        return "miniprogram"
    if "Dockerfile" in names:
        return "api"
    if "index.html" in names or "package.json" in names:
        return "web"
    return "unknown"


def _load_manifest(workspace: Path) -> dict:
    path = workspace / MANIFEST_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.agenthub-{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _target_path(workspace: Path, relative_path: str) -> Path | None:
    safe_path = _safe_relative_path(relative_path)
    if safe_path is None:
        return None
    target = workspace / safe_path
    resolved = target.resolve(strict=False)
    if resolved != workspace and workspace not in resolved.parents:
        return None
    return target


async def materialize_project_files(
    conversation_id: str,
    agent_id: str,
    files: list[GeneratedProjectFile],
) -> dict:
    """Atomically write generated files, update the manifest, and create one snapshot."""
    workspace = resolve_workspace(conversation_id)
    if workspace is None:
        raise ValueError("Invalid conversation ID")

    async with _workspace_lock(workspace):
        manifest = _load_manifest(workspace)
        manifest_files = {
            item["path"]: item
            for item in manifest.get("files", [])
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
        written = []
        timestamp = datetime.now(UTC).isoformat()
        for generated_file in files:
            target = _target_path(workspace, generated_file.path)
            if target is None:
                continue
            _atomic_write_text(target, generated_file.code)
            encoded = generated_file.code.encode("utf-8")
            entry = {
                "path": generated_file.path,
                "language": generated_file.language,
                "agent_id": agent_id,
                "size": len(encoded),
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "updated_at": timestamp,
            }
            manifest_files[generated_file.path] = entry
            written.append(entry)

        if not written:
            return {"files": [], "snapshot_id": "", "manifest": manifest}

        paths = set(manifest_files)
        manifest = {
            "schema_version": 1,
            "conversation_id": conversation_id,
            "project_type": _detect_project_type(paths),
            "updated_at": timestamp,
            "files": sorted(manifest_files.values(), key=lambda item: item["path"]),
        }
        _atomic_write_text(workspace / MANIFEST_PATH, json.dumps(manifest, ensure_ascii=False, indent=2))
        snapshot_id = await git_checkpoint(str(workspace), f"Generate {len(written)} file(s) with {agent_id}")
        return {"files": written, "snapshot_id": snapshot_id, "manifest": manifest}


def list_project_files(workspace: Path) -> list[dict]:
    files = []
    for root, directories, filenames in os.walk(workspace, followlinks=False):
        directories[:] = sorted(
            directory for directory in directories
            if directory not in IGNORED_TREE_DIRECTORIES
            and not (Path(root) / directory).is_symlink()
        )
        for filename in sorted(filenames):
            path = Path(root) / filename
            if path.is_symlink():
                continue
            relative = path.relative_to(workspace).as_posix()
            try:
                size = path.stat().st_size
            except OSError:
                continue
            files.append({
                "path": relative,
                "name": filename,
                "language": _language_from_path(relative),
                "size": size,
            })
            if len(files) >= MAX_PROJECT_FILES:
                return files
    return files


def read_project_file(workspace: Path, relative_path: str) -> dict:
    target = _target_path(workspace, relative_path)
    if target is None or not target.is_file():
        raise FileNotFoundError(relative_path)
    size = target.stat().st_size
    if size > MAX_FILE_READ_BYTES:
        raise ValueError("File is too large to preview")
    raw = target.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return {
                "path": _safe_relative_path(relative_path),
                "language": _language_from_path(relative_path),
                "size": size,
                "content": raw.decode(encoding),
            }
        except UnicodeDecodeError:
            continue
    raise ValueError("File is not a supported text file")


async def project_summary(workspace: Path) -> dict:
    return {
        "exists": True,
        "manifest": _load_manifest(workspace),
        "files": list_project_files(workspace),
        "snapshots": await git_log(str(workspace)),
    }


async def restore_project_snapshot(workspace: Path, snapshot_id: str) -> bool:
    if not re.fullmatch(r"[0-9a-fA-F]{7,64}", snapshot_id):
        return False
    async with _workspace_lock(workspace):
        snapshots = await git_log(str(workspace))
        full_hash = next(
            (item["hash"] for item in snapshots if item["hash"].startswith(snapshot_id)),
            None,
        )
        if full_hash is None:
            return False
        code, _, _ = await run_git_cmd(str(workspace), "cat-file", "-e", f"{full_hash}^{{commit}}")
        if code != 0:
            return False
        return await git_rollback_to(str(workspace), full_hash)
