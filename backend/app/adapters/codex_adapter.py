"""Codex local CLI adapter.

Each Agent Hub conversation owns an independent persisted Codex session. Only
completed assistant messages are forwarded to the chat; CLI diagnostics and
tool events stay in the backend logs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import AsyncGenerator

from app.adapters.base import AdapterConfig, AgentAdapter
from app.core.tenant_config import get_tenant_json, set_tenant_json

logger = logging.getLogger("codex_adapter")

DEFAULT_APP_BINARY = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
DEFAULT_WORKSPACE = Path(__file__).resolve().parents[3]
ALLOWED_SANDBOXES = {"read-only", "workspace-write"}
SESSION_CONFIG_KEY = "codex_sessions"
MAX_ERROR_LENGTH = 500


class CodexAdapter(AgentAdapter):
    """Run the authenticated Codex CLI as a local coding agent."""

    name = "Codex"
    adapter_type = "codex"
    description = "Codex 本机连接器 - 独立会话与工作区沙盒"

    def __init__(self, config: AdapterConfig):
        super().__init__(config)
        self.tenant_id = str(config.extra.get("_tenant_id", ""))
        self.binary = self._resolve_binary(str(config.extra.get("codex_path", "")))
        raw_workspace = str(config.extra.get("workspace", "")).strip()
        self.workspace = Path(raw_workspace).expanduser() if raw_workspace else DEFAULT_WORKSPACE
        self.workspace = self.workspace.resolve()
        raw_sandbox = str(config.extra.get("sandbox", "workspace-write"))
        self.sandbox = raw_sandbox if raw_sandbox in ALLOWED_SANDBOXES else "workspace-write"
        self.model = (config.model or "").strip()
        self._conversation_locks: dict[str, asyncio.Lock] = {}
        self._session_lock = asyncio.Lock()

    @staticmethod
    def _resolve_binary(value: str) -> Path | None:
        candidate = value.strip()
        if candidate:
            if os.sep not in candidate:
                resolved = shutil.which(candidate)
                return Path(resolved).resolve() if resolved else None
            return Path(candidate).expanduser().resolve()
        resolved = shutil.which("codex")
        if resolved:
            return Path(resolved).resolve()
        return DEFAULT_APP_BINARY.resolve() if DEFAULT_APP_BINARY.exists() else None

    def validate_config(self) -> tuple[bool, str]:
        if self.binary is None or not self.binary.is_file() or not os.access(self.binary, os.X_OK):
            return False, "未找到可执行的 Codex CLI"
        if not self.workspace.is_dir():
            return False, f"项目目录不存在: {self.workspace}"
        return True, ""

    def get_status(self) -> dict:
        status = super().get_status()
        status["extra"] = {
            "connection_mode": "local_cli",
            "codex_path": str(self.binary) if self.binary else "",
            "workspace": str(self.workspace),
            "sandbox": self.sandbox,
        }
        return status

    async def test_connection(self) -> tuple[bool, str]:
        """Check local authentication without spending a model request."""
        valid, error = self.validate_config()
        if not valid:
            return False, error
        try:
            process = await asyncio.create_subprocess_exec(
                str(self.binary),
                "login",
                "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),
                env=self._subprocess_env(),
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
        except TimeoutError:
            return False, "Codex 登录状态检查超时"
        except OSError as exc:
            return False, self._safe_error(str(exc))

        detail = (stdout + stderr).decode(errors="replace")
        detail = self._clean_cli_output(detail)
        if process.returncode == 0:
            return True, "Codex CLI 已登录"
        return False, detail or "Codex CLI 尚未登录"

    async def stream_reply(
        self,
        message: str,
        history: list[dict] = None,
        system_prompt: str = "",
        tools: list[dict] = None,
        conversation_id: str = None,
    ) -> AsyncGenerator[str, None]:
        del tools  # Codex uses its own local tool runtime.
        valid, error = self.validate_config()
        if not valid:
            yield f"[Codex 本机连接错误: {error}]"
            return

        lock_key = conversation_id or "__connection_test__"
        lock = self._conversation_locks.setdefault(lock_key, asyncio.Lock())
        async with lock:
            async for chunk in self._run_turn(
                message=message,
                history=history or [],
                system_prompt=system_prompt,
                conversation_id=conversation_id,
            ):
                yield chunk

    async def _run_turn(
        self,
        *,
        message: str,
        history: list[dict],
        system_prompt: str,
        conversation_id: str | None,
    ) -> AsyncGenerator[str, None]:
        session_key = self._session_key(conversation_id) if conversation_id else ""
        session_id = await self._load_session(session_key) if session_key else ""
        prompt = message if session_id else self._initial_prompt(message, history, system_prompt)
        command = self._build_command(session_id=session_id, ephemeral=not bool(conversation_id))

        process: asyncio.subprocess.Process | None = None
        stderr_task: asyncio.Task | None = None
        new_session_id = ""
        emitted_text = False
        event_errors: list[str] = []
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),
                env=self._subprocess_env(),
            )
            assert process.stdin is not None
            assert process.stdout is not None
            assert process.stderr is not None
            process.stdin.write(prompt.encode())
            await process.stdin.drain()
            process.stdin.close()
            stderr_task = asyncio.create_task(process.stderr.read())

            async with asyncio.timeout(max(self.config.timeout, 60)):
                while line := await process.stdout.readline():
                    try:
                        event = json.loads(line)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        logger.debug("Ignoring non-JSON Codex output: %r", line[:200])
                        continue

                    if event.get("type") == "thread.started":
                        new_session_id = str(event.get("thread_id", ""))

                    text = self._assistant_text(event)
                    if text:
                        emitted_text = True
                        yield text

                    if event.get("type") == "error":
                        event_errors.append(str(event.get("message", "Codex 执行失败")))

                return_code = await process.wait()
                stderr = await stderr_task
        except TimeoutError:
            if process is not None:
                await self._stop_process(process)
            yield "\n[Codex 本机连接错误: 执行超时]" if emitted_text else "[Codex 本机连接错误: 执行超时]"
            return
        except asyncio.CancelledError:
            if process is not None:
                await self._stop_process(process)
            raise
        except OSError as exc:
            yield f"[Codex 本机连接错误: {self._safe_error(str(exc))}]"
            return
        finally:
            if stderr_task is not None and not stderr_task.done():
                stderr_task.cancel()

        if return_code != 0:
            raw_error = "\n".join(event_errors) or stderr.decode(errors="replace")
            prefix = "\n" if emitted_text else ""
            yield f"{prefix}[Codex 本机连接错误: {self._clean_cli_output(raw_error)}]"
            return

        if session_key and new_session_id and new_session_id != session_id:
            await self._save_session(session_key, new_session_id)
        if not emitted_text:
            yield "[Codex 本机连接错误: 未收到自然语言回复]"

    def _build_command(self, *, session_id: str, ephemeral: bool) -> list[str]:
        assert self.binary is not None
        if session_id:
            command = [
                str(self.binary), "exec", "resume", session_id,
                "--json", "--skip-git-repo-check",
            ]
            if self.model:
                command.extend(["--model", self.model])
            command.append("-")
            return command

        command = [
            str(self.binary), "exec", "--json", "--color", "never",
            "--sandbox", self.sandbox, "--skip-git-repo-check",
            "--cd", str(self.workspace),
        ]
        if self.model:
            command.extend(["--model", self.model])
        if ephemeral:
            command.append("--ephemeral")
        command.append("-")
        return command

    def _session_key(self, conversation_id: str | None) -> str:
        return f"{self.workspace}:{conversation_id or ''}"

    async def _load_session(self, session_key: str) -> str:
        if not self.tenant_id or not session_key:
            return ""
        async with self._session_lock:
            sessions = get_tenant_json(self.tenant_id, SESSION_CONFIG_KEY, {}) or {}
            return str(sessions.get(session_key, ""))

    async def _save_session(self, session_key: str, session_id: str) -> None:
        if not self.tenant_id:
            return
        async with self._session_lock:
            sessions = get_tenant_json(self.tenant_id, SESSION_CONFIG_KEY, {}) or {}
            sessions[session_key] = session_id
            set_tenant_json(self.tenant_id, SESSION_CONFIG_KEY, sessions)

    @staticmethod
    def _assistant_text(event: dict) -> str:
        event_type = event.get("type")
        item = event.get("item") or {}
        if event_type == "item.completed" and item.get("type") == "agent_message":
            return str(item.get("text") or "")
        if event_type in {"agent_message", "agent_message.completed"}:
            return str(event.get("text") or event.get("message") or "")
        return ""

    @staticmethod
    def _initial_prompt(message: str, history: list[dict], system_prompt: str) -> str:
        sections: list[str] = []
        if system_prompt.strip():
            sections.append(system_prompt.strip())
        transcript: list[str] = []
        for item in history[-20:]:
            content = item.get("content", "")
            if isinstance(content, dict):
                content = content.get("text", "")
            content = str(content).strip()
            if not content:
                continue
            role = "用户" if item.get("role", item.get("sender")) == "user" else "助手"
            transcript.append(f"{role}: {content[:4000]}")
        if transcript:
            sections.append("此前对话记录:\n" + "\n".join(transcript))
        sections.append("当前用户请求:\n" + message)
        return "\n\n".join(sections)

    @staticmethod
    def _subprocess_env() -> dict[str, str]:
        return {**os.environ, "NO_COLOR": "1", "TERM": "dumb"}

    @classmethod
    def _clean_cli_output(cls, value: str) -> str:
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        lines = [line for line in lines if not line.startswith("WARNING: proceeding")]
        return cls._safe_error(" ".join(lines))

    @staticmethod
    def _safe_error(value: str) -> str:
        redacted = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-***", value)
        return redacted[:MAX_ERROR_LENGTH]

    @staticmethod
    async def _stop_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except TimeoutError:
            process.kill()
            await process.wait()
