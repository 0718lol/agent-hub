"""Sandbox dispatch regression tests."""

from unittest.mock import patch

import pytest

from app.core.sandbox_manager import SandboxManager


@pytest.mark.asyncio
async def test_host_subprocess_is_disabled_by_default():
    manager = SandboxManager()
    manager.enable_docker = False
    manager.e2b_api_key = ""

    with patch("app.core.sandbox_manager.settings.allow_unsandboxed_shell", False):
        result = await manager.execute("print('should not run')", "python")

    assert result["status"] == "error"
    assert "No isolated sandbox" in result["stderr"]
