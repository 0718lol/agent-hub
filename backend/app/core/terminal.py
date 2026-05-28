import asyncio
import os
import sys
import logging
from typing import Dict

logger = logging.getLogger("core_terminal")

class StatefulTerminal:
    """Represents a stateful, interactive shell terminal session (PowerShell on Windows, Bash/Sh on Linux)."""

    def __init__(self, conversation_id: str, cwd: str):
        self.conversation_id = conversation_id
        self.cwd = cwd
        self.process = None
        self.shell = "powershell.exe" if sys.platform == "win32" else "/bin/bash"
        self.args = ["-NoProfile", "-NonInteractive", "-Command", "-"] if sys.platform == "win32" else []

    async def start(self):
        """Launches the persistent shell process with stdout/stderr merged."""
        # Fallback on Linux if /bin/bash is not present
        if sys.platform != "win32" and not os.path.exists(self.shell):
            self.shell = "/bin/sh"

        logger.info(f"[StatefulTerminal] Starting stateful shell '{self.shell}' with args {self.args} for session {self.conversation_id} in {self.cwd}")
        
        # Merge stderr into stdout so we capture absolutely everything!
        self.process = await asyncio.create_subprocess_exec(
            self.shell,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=self.cwd,
            creationflags=0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW on Windows
        )

    async def execute(self, command: str, timeout: float = 15.0) -> str:
        """Executes a command statefully and reads output until the sentinel prints or timeout expires."""
        if not self.process or self.process.returncode is not None:
            # Re-launch if not active or dead
            await self.start()

        sentinel = "___STATEFUL_TERM_SENTINEL_OK___"
        
        # Build command sequence with sentinel print at the end
        if sys.platform == "win32":
            # PowerShell: execute command, then print sentinel
            full_command = f"{command}\r\nWrite-Output \"{sentinel}\"\r\n"
        else:
            # Bash/Sh: execute command, then print sentinel
            full_command = f"{command}\necho \"{sentinel}\"\n"

        logger.debug(f"[StatefulTerminal] Sending command: {command}")
        self.process.stdin.write(full_command.encode("utf-8", errors="replace"))
        await self.process.stdin.drain()

        output_lines = []
        try:
            while True:
                # Read line by line with timeout protection
                line_bytes = await asyncio.wait_for(self.process.stdout.readline(), timeout=timeout)
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace")
                
                # Check if sentinel is reached
                if sentinel in line:
                    break
                
                output_lines.append(line)
        except asyncio.TimeoutError:
            logger.warning(f"[StatefulTerminal] Command timed out after {timeout} seconds")
            output_lines.append(f"\n⚠️ [Stateful Command timed out after {timeout} seconds]")

        # Clean and join the output
        joined_output = "".join(output_lines)
        return joined_output

    async def stop(self):
        """Terminates the shell process gracefully."""
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except Exception as e:
                logger.error(f"[StatefulTerminal] Error terminating terminal process: {e}")
            self.process = None


class StatefulTerminalManager:
    """Manages active, persistent terminal shell sessions mapped to conversation IDs."""

    def __init__(self):
        self.sessions: Dict[str, StatefulTerminal] = {}

    async def get_or_create_session(self, conversation_id: str, default_cwd: str) -> StatefulTerminal:
        """Fetch existing stateful shell or start a new persistent session."""
        if conversation_id not in self.sessions:
            terminal = StatefulTerminal(conversation_id, default_cwd)
            await terminal.start()
            self.sessions[conversation_id] = terminal
        return self.sessions[conversation_id]

    async def close_session(self, conversation_id: str):
        """Terminates a specific session's terminal process."""
        if conversation_id in self.sessions:
            terminal = self.sessions.pop(conversation_id)
            await terminal.stop()

    async def close_all(self):
        """Cleanly stops all persistent shell processes on program exit."""
        logger.info("[StatefulTerminalManager] Cleaning up all stateful terminal processes...")
        for conversation_id, terminal in list(self.sessions.items()):
            try:
                await terminal.stop()
            except Exception:
                pass
        self.sessions.clear()


stateful_terminal_manager = StatefulTerminalManager()
