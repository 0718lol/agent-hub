import os
import sys
import json
import uuid
import pytest
import asyncio
from unittest.mock import patch, MagicMock

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.config import settings, obfuscate_key, deobfuscate_key
from app.core.mcp_client import SystemMCPServer


def test_obfuscation():
    """Verify that sensitive API Keys are safely obfuscated and deobfuscated."""
    original_key = "sk-proj-1234567890abcdefghijklmnopqrstuvwxyz"
    obfuscated = obfuscate_key(original_key)
    
    assert obfuscated.startswith("enc::")
    assert original_key not in obfuscated
    
    deobfuscated = deobfuscate_key(obfuscated)
    assert deobfuscated == original_key


@pytest.mark.asyncio
async def test_path_traversal_blocking():
    """Verify that SystemMCPServer prevents any relative or symlinked path traversal."""
    server = SystemMCPServer()
    conversation_id = f"test-session-{uuid.uuid4().hex}"
    
    # Base sandbox directory where files should belong
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    sandbox_dir = os.path.join(workspace_dir, "agenthub_export", conversation_id)
    os.makedirs(sandbox_dir, exist_ok=True)
    
    try:
        # 1. Attempt standard relative segment traversal
        res_list = await server.call_tool(
            "workspace_list_dir", 
            {"path": "../../../backend"}, 
            conversation_id=conversation_id
        )
        assert res_list.get("isError") is True
        assert "Path traversal protection triggered" in res_list["content"][0]["text"]
        
        # 2. Attempt traversal on read file
        res_read = await server.call_tool(
            "workspace_read_file", 
            {"path": "../../../backend/app/main.py"}, 
            conversation_id=conversation_id
        )
        assert res_read.get("isError") is True
        assert "Path traversal protection triggered" in res_read["content"][0]["text"]
        
        # 3. Attempt traversal on write file
        res_write = await server.call_tool(
            "workspace_write_file", 
            {"path": "../../../backend/app/hack.py", "content": "print(1)"}, 
            conversation_id=conversation_id
        )
        assert res_write.get("isError") is True
        assert "Path traversal protection triggered" in res_write["content"][0]["text"]
    finally:
        # Cleanup created sandbox dir
        try:
            import shutil
            shutil.rmtree(sandbox_dir, ignore_errors=True)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_local_rce_blocking():
    """Verify that when Docker is disabled, running commands without permission is strictly blocked."""
    server = SystemMCPServer()
    conversation_id = f"test-session-{uuid.uuid4().hex}"
    
    # Temporarily force Docker and non-Docker fallback behavior
    with patch.dict(os.environ, {"AGENTHUB_DOCKER_SANDBOX": "false"}):
        with patch.object(settings, "allow_unsandboxed_shell", False):
            res = await server.call_tool(
                "workspace_run_command", 
                {"command": "echo 'Pwned'"}, 
                conversation_id=conversation_id
            )
            assert res.get("isError") is True
            assert "安全限制：未启用或未检测到 Docker 环境" in res["content"][0]["text"]


@pytest.mark.asyncio
async def test_local_rce_execution_allowed_and_script_wrapped():
    """Verify that when allow_unsandboxed_shell is True, the commands run via temporary script wrapping."""
    server = SystemMCPServer()
    conversation_id = f"test-session-{uuid.uuid4().hex}"
    
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    sandbox_dir = os.path.join(workspace_dir, "agenthub_export", conversation_id)
    os.makedirs(sandbox_dir, exist_ok=True)

    # Initialize a dummy git repository inside sandbox so checkpoints work without throwing fatal error
    proc_git = await asyncio.create_subprocess_exec(
        "git", "init",
        cwd=sandbox_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await proc_git.communicate()

    # Configure git username/email so commits don't fail
    await (await asyncio.create_subprocess_exec("git", "config", "user.name", "TestUser", cwd=sandbox_dir)).communicate()
    await (await asyncio.create_subprocess_exec("git", "config", "user.email", "test@test.com", cwd=sandbox_dir)).communicate()
    # Add an empty file and commit it so there's an initial commit
    with open(os.path.join(sandbox_dir, "init.txt"), "w") as f:
        f.write("init")
    await (await asyncio.create_subprocess_exec("git", "add", ".", cwd=sandbox_dir)).communicate()
    await (await asyncio.create_subprocess_exec("git", "commit", "-m", "init", cwd=sandbox_dir)).communicate()

    try:
        with patch.dict(os.environ, {"AGENTHUB_DOCKER_SANDBOX": "false"}):
            with patch.object(settings, "allow_unsandboxed_shell", True):
                res = await server.call_tool(
                    "workspace_run_command",
                    {"command": "echo SuccessRemediation"},
                    conversation_id=conversation_id
                )
                
                # It should not return RCE security error
                assert res.get("isError") is not True or "安全限制" not in res["content"][0]["text"]
                # Output should contain the expected execution print-back
                assert "SuccessRemediation" in res["content"][0]["text"]
                
                # Check that temporary script file is cleaned up and deleted completely
                files_left = os.listdir(sandbox_dir)
                for f in files_left:
                    assert not f.startswith("temp_run_")
    finally:
        # Cleanup created sandbox dir
        try:
            import shutil
            shutil.rmtree(sandbox_dir, ignore_errors=True)
        except Exception:
            pass
