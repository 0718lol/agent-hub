import asyncio
import os
import re
import sys


def safe_decode(data: bytes) -> str:
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("gb18030")
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="replace")

async def run_git_cmd(cwd: str, *args) -> tuple[int, str, str]:

    """Helper to safely run a git command asynchronously in the target sandboxed workspace."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            creationflags=0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW on Windows
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, safe_decode(stdout).strip(), safe_decode(stderr).strip()

    except Exception as e:
        return -1, "", f"Failed to execute git command: {e}"

async def git_init(sandbox_dir: str) -> bool:
    """Initialize a git repository in the sandboxed workspace if not already initialized."""
    dot_git = os.path.join(sandbox_dir, ".git")
    if os.path.exists(dot_git):
        return True

    os.makedirs(sandbox_dir, exist_ok=True)

    # 1. git init
    code, _, err = await run_git_cmd(sandbox_dir, "init")
    if code != 0:
        print(f"[GitSandbox] git init failed: {err}")
        return False

    # 2. Configure user.name and user.email locally to avoid global lock issues
    await run_git_cmd(sandbox_dir, "config", "user.name", "AgentHub")
    await run_git_cmd(sandbox_dir, "config", "user.email", "agent@agenthub.local")

    # 3. Create a basic ignore file if not exists
    ignore_file = os.path.join(sandbox_dir, ".gitignore")
    if not os.path.exists(ignore_file):
        with open(ignore_file, "w", encoding="utf-8") as f:
            f.write("*.log\n")

    # 4. Create initial commit
    await run_git_cmd(sandbox_dir, "add", ".")
    await run_git_cmd(sandbox_dir, "commit", "-m", "Initial Commit: 沙盒工作区版本控制开启")
    return True

async def git_is_dirty(sandbox_dir: str) -> bool:
    """Check if there are any uncommitted changes (dirty working tree)."""
    code, out, _ = await run_git_cmd(sandbox_dir, "status", "--porcelain")
    return code == 0 and bool(out)

async def git_checkpoint(sandbox_dir: str, message: str) -> str:
    """Stage all changes and commit. Returns the commit hash or empty string on failure."""
    await git_init(sandbox_dir)

    # Check if dirty first
    dirty = await git_is_dirty(sandbox_dir)
    if not dirty:
        # If clean, fetch current HEAD hash
        _, out, _ = await run_git_cmd(sandbox_dir, "rev-parse", "HEAD")
        return out

    # Stage and commit
    await run_git_cmd(sandbox_dir, "add", ".")
    code, _, err = await run_git_cmd(sandbox_dir, "commit", "-m", message)
    if code != 0:
        print(f"[GitSandbox] Commit failed: {err}")
        # Fetch current HEAD as fallback
        _, out, _ = await run_git_cmd(sandbox_dir, "rev-parse", "HEAD")
        return out

    # Fetch latest hash
    _, out, _ = await run_git_cmd(sandbox_dir, "rev-parse", "HEAD")
    return out

async def git_rollback(sandbox_dir: str) -> bool:
    """Hard-rollback all modifications since the last commit (discard dirty work)."""
    return await _reset_workspace(sandbox_dir, "HEAD")

async def git_rollback_to(sandbox_dir: str, commit_hash: str) -> bool:
    """Force roll back the workspace to a specific commit checkpoint."""
    if not re.fullmatch("[0-9a-fA-F]{7,64}", commit_hash):
        return False

    options = _workspace_git_options(sandbox_dir)
    if not options:
        return False
    code, keys, _ = await run_git_cmd(
        sandbox_dir, *options, "config", "--local", "--no-includes", "--name-only", "--list",
    )
    # A reset can run a worktree filter or fetch missing objects using repository commands.
    if code != 0 or any(
        key.startswith(("filter.", "include.", "includeif.")) or key == "extensions.worktreeconfig"
        or key.endswith(".promisor")
        for key in keys.casefold().splitlines()
    ):
        return False
    return await _reset_workspace(sandbox_dir, commit_hash)


def _workspace_git_options(sandbox_dir: str) -> tuple[str, ...]:
    dot_git = os.path.join(sandbox_dir, ".git")
    if not os.path.isdir(dot_git) or os.path.islink(dot_git):
        return ()
    return ("--git-dir=.git", "--work-tree=.", "-c", "core.fsmonitor=false", "-c", f"core.hooksPath={os.devnull}")


async def _reset_workspace(sandbox_dir: str, revision: str) -> bool:
    options = _workspace_git_options(sandbox_dir)
    if not options:
        return False
    code, _, _ = await run_git_cmd(sandbox_dir, *options, "reset", "--hard", revision, "--")
    if code != 0:
        return False
    code, _, _ = await run_git_cmd(sandbox_dir, *options, "clean", "-fd")
    return code == 0

async def git_log(sandbox_dir: str) -> list[dict]:
    """Query git commit log structured as a list of commits."""
    options = _workspace_git_options(sandbox_dir)
    if not options:
        return []

    # Query log: hash|unix_timestamp|message
    code, out, _ = await run_git_cmd(sandbox_dir, *options, "log", "--pretty=format:%H|%ct|%s")
    if code != 0 or not out:
        return []

    commits = []
    for line in out.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = line.split("|", 2)
        if len(parts) >= 3:
            commits.append({
                "hash": parts[0],
                "timestamp": int(parts[1]),
                "message": parts[2]
            })
    return commits
