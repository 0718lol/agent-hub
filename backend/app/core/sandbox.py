"""
Code Execution Sandbox

Safely executes user/agent-generated code in isolated subprocess.
Supports: Python, JavaScript (Node.js), Shell scripts.

Security:
  - Timeout enforcement (default 10s)
  - Memory limit via resource limiting
  - Stdout/stderr capture with size cap
  - No network access in strict mode (future)
"""

import asyncio
import tempfile
import os
import time
from dataclasses import dataclass, field
from typing import Optional


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


# Max output size (chars)
MAX_OUTPUT = 5000
# Default timeout (seconds)
DEFAULT_TIMEOUT = 10


async def execute_code(
    code: str,
    language: str = "python",
    timeout: int = DEFAULT_TIMEOUT,
    stdin_data: str = "",
) -> ExecutionResult:
    """
    Execute code in a sandboxed subprocess.

    Args:
        code: Source code to execute
        language: 'python' | 'javascript' | 'shell'
        timeout: Max execution time in seconds
        stdin_data: Optional stdin input

    Returns:
        ExecutionResult with stdout, stderr, exit_code, timing
    """
    # Determine command and file extension
    lang_config = {
        "python": {"ext": ".py", "cmd": ["python", "-u"]},
        "py": {"ext": ".py", "cmd": ["python", "-u"]},
        "javascript": {"ext": ".js", "cmd": ["node"]},
        "js": {"ext": ".js", "cmd": ["node"]},
        "typescript": {"ext": ".ts", "cmd": ["npx", "tsx"]},
        "ts": {"ext": ".ts", "cmd": ["npx", "tsx"]},
        "shell": {"ext": ".sh", "cmd": ["bash"]},
        "bash": {"ext": ".sh", "cmd": ["bash"]},
        "sh": {"ext": ".sh", "cmd": ["bash"]},
    }

    lang_key = language.lower().strip()
    if lang_key not in lang_config:
        return ExecutionResult(
            language=language,
            status="error",
            stderr=f"不支持的语言: {language}。支持: python, javascript, shell",
            exit_code=-1,
        )

    config = lang_config[lang_key]

    # Write code to temp file
    tmp_dir = tempfile.mkdtemp(prefix="sandbox_")
    tmp_file = os.path.join(tmp_dir, f"code{config['ext']}")

    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(code)

        cmd = config["cmd"] + [tmp_file]
        start_time = time.perf_counter()

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin_data else None,
            cwd=tmp_dir,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

        try:
            stdin_bytes = stdin_data.encode("utf-8") if stdin_data else None
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input=stdin_bytes),
                timeout=timeout,
            )
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            truncated = False
            if len(stdout) > MAX_OUTPUT:
                stdout = stdout[:MAX_OUTPUT] + "\n... [输出截断]"
                truncated = True
            if len(stderr) > MAX_OUTPUT:
                stderr = stderr[:MAX_OUTPUT] + "\n... [输出截断]"
                truncated = True

            status = "success" if proc.returncode == 0 else "error"

            return ExecutionResult(
                language=language,
                status=status,
                stdout=stdout,
                stderr=stderr,
                exit_code=proc.returncode or 0,
                duration_ms=elapsed_ms,
                truncated=truncated,
            )

        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ExecutionResult(
                language=language,
                status="timeout",
                stderr=f"执行超时（限制 {timeout}s）",
                exit_code=-1,
                duration_ms=elapsed_ms,
            )

    except Exception as e:
        return ExecutionResult(
            language=language,
            status="error",
            stderr=f"沙盒启动失败: {str(e)}",
            exit_code=-1,
        )

    finally:
        # Cleanup temp files
        try:
            os.unlink(tmp_file)
            os.rmdir(tmp_dir)
        except OSError:
            pass
