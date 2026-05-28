import asyncio
import os
import sys
import json
import shutil

# Setup import path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Reconfigure stdout to support utf-8 on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.core.git_sandbox import git_init, git_checkpoint, git_rollback, git_log, git_rollback_to
from app.core.mcp_client import mcp_manager

async def run_git_sandbox_testing():
    print("====================================================")
    print("[START] Plan E: Sandbox Git-level Versioning & Autorecovery Regression Test")
    print("====================================================\n")

    test_conv_id = "conv_test_git_sandbox_milestone"
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    sandbox_dir = os.path.join(workspace_dir, "agenthub_export", test_conv_id)
    
    # 0. Clean up sandbox
    if os.path.exists(sandbox_dir):
        try:
            # Git folders can have read-only permissions on files
            shutil.rmtree(sandbox_dir)
        except Exception:
            # fallback clean
            pass
            
    os.makedirs(sandbox_dir, exist_ok=True)

    # 1. Test Git Init
    print("[Step 1] Initializing Git repository in sandbox...")
    success = await git_init(sandbox_dir)
    assert success
    dot_git_dir = os.path.join(sandbox_dir, ".git")
    assert os.path.exists(dot_git_dir)
    print("  SUCCESS: Git repository successfully initialized.")

    # 2. Test Git commits log
    print("\n[Step 2] Fetching initial commit logs...")
    logs = await git_log(sandbox_dir)
    assert len(logs) > 0
    print(f"  Initial Commit Message: {logs[0]['message']}")
    print(f"  Initial Commit Hash: {logs[0]['hash']}")
    print("  SUCCESS: Initial commit parsed and structured properly.")

    # 3. Test Auto-healing Rollback for Syntax Errors (implicit Quality Gate)
    print("\n[Step 3] Simulating Agent writing Python code with SYNTAX ERROR...")
    bad_code = "def hello_broken_syntax(\n    print('Missing closing parenthesis!'"
    
    # Execute workspace_write_file tool with syntax error code
    write_args = {
        "path": "broken_syntax.py",
        "content": bad_code
    }
    
    res = await mcp_manager.execute_tool("SystemServer__workspace_write_file", write_args, conversation_id=test_conv_id)
    assert res.get("isError", False)
    content_list = res.get("content", [])
    assert len(content_list) > 0
    print(f"  Expected Auto-healing rollback error message:")
    print(f"  ------------------------------------------------")
    print(content_list[0]['text'].strip())
    print(f"  ------------------------------------------------")
    assert "Syntax Error" in content_list[0]['text']
    
    # Verify the broken syntax file was physically rolled back and deleted!
    broken_file_path = os.path.join(sandbox_dir, "broken_syntax.py")
    assert not os.path.exists(broken_file_path)
    print("  SUCCESS: Sandbox successfully rolled back and deleted the syntactically invalid file!")

    # 4. Test Auto-healing Rollback for Terminal Command Failures
    print("\n[Step 4] Simulating terminal command FAILURE (non-zero exit code)...")
    
    # First, write a healthy file to have a successful commit
    write_args_ok = {
        "path": "healthy.py",
        "content": "print('Hello healthy Python file')"
    }
    res_ok = await mcp_manager.execute_tool("SystemServer__workspace_write_file", write_args_ok, conversation_id=test_conv_id)
    assert not res_ok.get("isError", False)
    
    # Now run a command that fails (e.g. exit 1 or run python on a non-existent file)
    cmd_args = {
        "command": "python non_existent_file.py"
    }
    cmd_res = await mcp_manager.execute_tool("SystemServer__workspace_run_command", cmd_args, conversation_id=test_conv_id)
    assert cmd_res.get("isError", False)
    cmd_content = cmd_res.get("content", [])
    assert len(cmd_content) > 0
    print(f"  Expected Auto-healing command rollback error message:")
    print(f"  ------------------------------------------------")
    print(cmd_content[0]['text'].strip())
    print(f"  ------------------------------------------------")
    assert "指令执行失败！" in cmd_content[0]['text']
    
    # 5. Fetch total sandbox version log list
    print("\n[Step 5] Retrieving full sandbox commit timeline...")
    final_logs = await git_log(sandbox_dir)
    print(f"  Timeline has {len(final_logs)} active commits:")
    for i, commit in enumerate(final_logs):
        print(f"    [{i}] {commit['hash'][:7]} - {commit['message']}")
        
    assert len(final_logs) >= 2 # Initial commit + Success healthy.py write commit
    print("  SUCCESS: Sandbox Git commits timeline successfully queried.")

    # Cleanup sandbox files
    try:
        shutil.rmtree(sandbox_dir)
    except Exception:
        pass

    print("\n====================================================")
    print("🎉 SUCCESS: Plan E Sandbox Git versioning & self-healing regression suite passed with 100% PASS!")
    print("====================================================")

if __name__ == "__main__":
    asyncio.run(run_git_sandbox_testing())
