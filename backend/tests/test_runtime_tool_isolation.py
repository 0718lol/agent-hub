"""Agent runtime tools must use the configured isolation manager."""

from unittest.mock import AsyncMock, patch

import pytest

from app.tools.code_interpreter_tools import E2BPythonInterpreterTool
from app.tools.stateful_terminal_tool import StatefulTerminalTool


@pytest.mark.asyncio
async def test_python_interpreter_uses_sandbox_manager():
    result = {"status": "success", "stdout": "42\n", "stderr": "", "exit_code": 0}
    with patch(
        "app.tools.code_interpreter_tools.sandbox_manager.execute",
        new=AsyncMock(return_value=result),
    ) as execute:
        response = await E2BPythonInterpreterTool().execute({"code": "print(42)"})

    assert response.success
    execute.assert_awaited_once()
    assert execute.await_args.kwargs == {"language": "python", "timeout": 15}


@pytest.mark.asyncio
async def test_terminal_uses_project_workspace(tmp_path):
    result = {"status": "success", "stdout": "ok\n", "stderr": "", "exit_code": 0}
    with (
        patch(
            "app.tools.stateful_terminal_tool.sandbox_manager.execute",
            new=AsyncMock(return_value=result),
        ) as execute,
        patch(
            "app.tools.stateful_terminal_tool.resolve_workspace",
            return_value=tmp_path,
        ),
    ):
        response = await StatefulTerminalTool().execute(
            {"command": "printf ok", "conversation_id": "conv-1"}
        )

    assert response.success
    execute.assert_awaited_once_with(
        "printf ok",
        language="shell",
        timeout=120,
        workspace=tmp_path,
    )


@pytest.mark.asyncio
async def test_terminal_rejects_invalid_conversation_id():
    with patch("app.tools.stateful_terminal_tool.resolve_workspace", return_value=None):
        response = await StatefulTerminalTool().execute(
            {"command": "ls", "conversation_id": "../outside"}
        )

    assert not response.success
    assert "ID" in response.error
