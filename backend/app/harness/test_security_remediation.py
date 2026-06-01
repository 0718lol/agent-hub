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
import logging
_logger = logging.getLogger("test_security_remediation")


def test_obfuscation():
    """Verify that sensitive API Keys are safely obfuscated and deobfuscated."""
    original_key = "sk-proj-1234567890abcdefghijklmnopqrstuvwxyz"
    obfuscated = obfuscate_key(original_key)
    
    assert obfuscated.startswith("fnt::")
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
        except Exception as e:
            _logger.warning(f"Failed to clean up sandbox dir: {e}")


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
        except Exception as e:
            _logger.warning(f"Failed to clean up sandbox dir: {e}")


@pytest.mark.asyncio
async def test_local_rce_cpu_timeout():
    """Verify that subprocesses exceeding the execution timeout are forcefully killed."""
    server = SystemMCPServer()
    conversation_id = f"test-session-{uuid.uuid4().hex}"
    
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    sandbox_dir = os.path.join(workspace_dir, "agenthub_export", conversation_id)
    os.makedirs(sandbox_dir, exist_ok=True)

    # Git initialization
    await (await asyncio.create_subprocess_exec("git", "init", cwd=sandbox_dir)).communicate()
    await (await asyncio.create_subprocess_exec("git", "config", "user.name", "TestUser", cwd=sandbox_dir)).communicate()
    await (await asyncio.create_subprocess_exec("git", "config", "user.email", "test@test.com", cwd=sandbox_dir)).communicate()
    with open(os.path.join(sandbox_dir, "init.txt"), "w") as f:
        f.write("init")
    await (await asyncio.create_subprocess_exec("git", "add", ".", cwd=sandbox_dir)).communicate()
    await (await asyncio.create_subprocess_exec("git", "commit", "-m", "init", cwd=sandbox_dir)).communicate()

    # 使用 Python 跨平台挂起命令，避免 Windows timeout 命令在输入重定向下直接崩溃退出
    sleep_cmd = f'"{sys.executable}" -c "import time; time.sleep(30)"'

    old_timeout = settings.shell_timeout
    old_allow = settings.allow_unsandboxed_shell
    try:
        settings.shell_timeout = 2.0
        settings.allow_unsandboxed_shell = True
        
        with patch.dict(os.environ, {"AGENTHUB_DOCKER_SANDBOX": "false"}):
            start_time = asyncio.get_event_loop().time()
            res = await server.call_tool(
                "workspace_run_command",
                {"command": sleep_cmd},
                conversation_id=conversation_id
            )
            elapsed = asyncio.get_event_loop().time() - start_time
            
            assert elapsed < 10.0 # Must not run full 30s
            assert res.get("isError") is True
            assert "超过了物理资源配额硬超时限制" in res["content"][0]["text"]
    finally:
        settings.shell_timeout = old_timeout
        settings.allow_unsandboxed_shell = old_allow
        try:
            import shutil
            shutil.rmtree(sandbox_dir, ignore_errors=True)
        except Exception as e:
            _logger.warning(f"Failed to clean up sandbox dir: {e}")


@pytest.mark.asyncio
async def test_local_rce_memory_exhaustion():
    """Verify that processes allocating excessive memory are terminated by ulimit or Job Objects."""
    server = SystemMCPServer()
    conversation_id = f"test-session-{uuid.uuid4().hex}"
    
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    sandbox_dir = os.path.join(workspace_dir, "agenthub_export", conversation_id)
    os.makedirs(sandbox_dir, exist_ok=True)

    # Git initialization
    await (await asyncio.create_subprocess_exec("git", "init", cwd=sandbox_dir)).communicate()
    await (await asyncio.create_subprocess_exec("git", "config", "user.name", "TestUser", cwd=sandbox_dir)).communicate()
    await (await asyncio.create_subprocess_exec("git", "config", "user.email", "test@test.com", cwd=sandbox_dir)).communicate()
    with open(os.path.join(sandbox_dir, "init.txt"), "w") as f:
        f.write("init")
    await (await asyncio.create_subprocess_exec("git", "add", ".", cwd=sandbox_dir)).communicate()
    await (await asyncio.create_subprocess_exec("git", "commit", "-m", "init", cwd=sandbox_dir)).communicate()

    # Memory allocation python payload (tries to allocate 60MB)
    py_payload = f'"{sys.executable}" -c "import time; x = bytearray(60 * 1024 * 1024); time.sleep(0.5); print(len(x))"'

    old_mem_limit = settings.shell_memory_limit_mb
    old_allow = settings.allow_unsandboxed_shell
    try:
        settings.shell_memory_limit_mb = 15
        settings.allow_unsandboxed_shell = True
        
        with patch.dict(os.environ, {"AGENTHUB_DOCKER_SANDBOX": "false"}):
            res = await server.call_tool(
                "workspace_run_command",
                {"command": py_payload},
                conversation_id=conversation_id
            )
            
            # Since 60MB allocation >> 15MB limit, the process must fail or be aborted
            assert res.get("isError") is True
            assert "指令执行失败" in res["content"][0]["text"]
    finally:
        settings.shell_memory_limit_mb = old_mem_limit
        settings.allow_unsandboxed_shell = old_allow
        try:
            import shutil
            shutil.rmtree(sandbox_dir, ignore_errors=True)
        except Exception as e:
            _logger.warning(f"Failed to clean up sandbox dir: {e}")


@pytest.mark.asyncio
async def test_subprocess_sandbox_memory_limit():
    """Verify that SubprocessSandbox terminates code allocating excessive memory."""
    from app.core.sandbox_manager import sandbox_manager
    old_enable_docker = sandbox_manager.enable_docker
    old_mem_limit = settings.shell_memory_limit_mb
    
    try:
        sandbox_manager.enable_docker = False
        settings.shell_memory_limit_mb = 15  # 15MB limit
        
        # Payload tries to allocate 60MB
        payload = "x = bytearray(60 * 1024 * 1024)"
        res = await sandbox_manager.execute(payload, language="python", timeout=5)
        
        assert res.get("status") == "error"
    finally:
        sandbox_manager.enable_docker = old_enable_docker
        settings.shell_memory_limit_mb = old_mem_limit


@pytest.mark.asyncio
async def test_subprocess_sandbox_timeout():
    """Verify that SubprocessSandbox forcefully kills hanging code execution."""
    from app.core.sandbox_manager import sandbox_manager
    old_enable_docker = sandbox_manager.enable_docker
    
    try:
        sandbox_manager.enable_docker = False
        
        payload = "import time\ntime.sleep(30)"
        start_time = asyncio.get_event_loop().time()
        res = await sandbox_manager.execute(payload, language="python", timeout=2)
        elapsed = asyncio.get_event_loop().time() - start_time
        
        assert elapsed < 10.0  # Must not run full 30s
        assert res.get("status") == "timeout"
        assert "超时" in res.get("stderr", "")
    finally:
        sandbox_manager.enable_docker = old_enable_docker


def test_quality_gate_multi_block():
    """Verify that QualityGate scans all blocks and fails if a single block fails (worst-case)."""
    from app.core.quality_gate import QualityGate
    gate = QualityGate(enabled=True)
    
    # HTML block is clean/valid, but Python block is invalid (contains placeholders like TODO/...)
    text = (
        "Here is the HTML frontend:\n"
        "```html\n"
        "<!DOCTYPE html><html><head><meta name='viewport' content='width=device-width'></head>"
        "<body class='app'><h1>Test</h1></body></html>\n"
        "```\n\n"
        "And here is the broken Python script:\n"
        "```python\n"
        "def main():\n"
        "    # TODO: implement this block\n"
        "    ...\n"
        "```\n"
    )
    
    report = gate.evaluate(text)
    # Even though HTML is valid, python is broken, so overall passed must be False
    assert report.passed is False
    # Score should reflect the worst score
    assert report.score < 1.0
    # Must capture the suggestion from the broken Python block
    assert any("检测到占位符" in s or "占位符" in s for s in report.suggestions) or any("检测到占位符" in r.message for r in report.results if not r.passed)


def test_context_optimizer_traceback_preservation():
    """Verify that ContextOptimizer preserves the error stack trace when truncating long texts."""
    from app.core.llm_client import ContextOptimizer
    
    traceback_log = (
        "Traceback (most recent call last):\n"
        "  File \"app.py\", line 10, in main\n"
        "    result = 1 / 0\n"
        "ZeroDivisionError: division by zero"
    )
    
    # Construct a huge string exceeding 6000 chars containing the error in the middle
    huge_str = "A" * 5000 + "\n" + traceback_log + "\n" + "B" * 5000
    
    compressed = ContextOptimizer.compress_single_message(huge_str, max_chars=3000)
    
    # Assert traceback is explicitly preserved in the compressed content
    assert "拦截并抽取的关键报错" in compressed
    assert "ZeroDivisionError" in compressed
    assert len(compressed) < 10000


def test_rag_semantic_splitter():
    """Verify that the recursive character text splitter respects semantic limits and overlap."""
    from app.core.rag_engine import split_text
    
    sample_text = (
        "段落一。这是第一句。这是第二句。\n\n"
        "段落二！这是第三句！这是第四句！\n\n"
        "段落三？这是第五句？这是第六句？"
    )
    
    chunks = split_text(sample_text, chunk_size=30, overlap=5)
    
    # Assert that all chunks are non-empty and respect maximum sizing
    assert len(chunks) > 0
    for chunk in chunks:
        assert len(chunk) <= 30
        assert chunk.strip() != ""



@pytest.mark.asyncio
async def test_path_traversal_non_existent_blocking():
    """Verify that SystemMCPServer prevents relative traversals on non-existent directories/files."""
    server = SystemMCPServer()
    conversation_id = f"test-session-{uuid.uuid4().hex}"
    
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    sandbox_dir = os.path.join(workspace_dir, "agenthub_export", conversation_id)
    os.makedirs(sandbox_dir, exist_ok=True)
    
    try:
        # 1. Traversal using non-existent directory structure targeting existing folder outside sandbox
        res_list = await server.call_tool(
            "workspace_list_dir", 
            {"path": "nonexistent/../../../../backend"}, 
            conversation_id=conversation_id
        )
        assert res_list.get("isError") is True
        assert "Path traversal protection triggered" in res_list["content"][0]["text"]
        
        # 2. Traversal on read non-existent file path resolved outside
        res_read = await server.call_tool(
            "workspace_read_file", 
            {"path": "nonexistent/../../../../backend/app/main.py"}, 
            conversation_id=conversation_id
        )
        assert res_read.get("isError") is True
        assert "Path traversal protection triggered" in res_read["content"][0]["text"]
        
        # 3. Traversal on write non-existent file path resolved outside
        res_write = await server.call_tool(
            "workspace_write_file", 
            {"path": "nonexistent/../../../../backend/app/hack.py", "content": "print(1)"}, 
            conversation_id=conversation_id
        )
        assert res_write.get("isError") is True
        assert "Path traversal protection triggered" in res_write["content"][0]["text"]
    finally:
        # Cleanup
        try:
            import shutil
            shutil.rmtree(sandbox_dir, ignore_errors=True)
        except Exception as e:
            _logger.warning(f"Failed to clean up sandbox dir: {e}")



