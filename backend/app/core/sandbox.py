"""
Code Execution Sandbox — Resilient secure forwarding layer to sandbox_manager.
"""

from dataclasses import dataclass


@dataclass
class ExecutionResult:
    """Result of a sandboxed code execution."""
    language: str
    status: str  # "success" | "error" | "timeout"
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    duration_ms: int = 0
    truncated: bool = False

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "status": self.status,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "truncated": self.truncated,
        }


# Default timeout (seconds)
DEFAULT_TIMEOUT = 10


async def execute_code(
    code: str,
    language: str = "python",
    timeout: int = DEFAULT_TIMEOUT,
    stdin_data: str = "",
    quota_key: str | None = None,
) -> ExecutionResult:
    """
    Execute code in a secure sandboxed execution rail.
    """
    from app.core.sandbox_manager import sandbox_manager

    # Delegate execution directly to resilient sandbox manager
    res = await sandbox_manager.execute(
        code=code,
        language=language,
        timeout=timeout,
        stdin_data=stdin_data,
        quota_key=quota_key,
    )

    # Wrap the output dictionary into the standard backward-compatible ExecutionResult instance
    return ExecutionResult(
        language=res.get("language", language),
        status=res.get("status", "error"),
        stdout=res.get("stdout", ""),
        stderr=res.get("stderr", ""),
        exit_code=res.get("exit_code", -1),
        duration_ms=res.get("duration_ms", 0),
        truncated=res.get("truncated", False),
    )
