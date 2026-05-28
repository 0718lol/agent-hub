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

from app.core.mcp_client import mcp_manager

async def run_mcp_testing():
    print("====================================================")
    print("[START] Plan D: Model Context Protocol (MCP) Integration Regression Test")
    print("====================================================\n")

    test_conv_id = "conv_test_mcp_milestone"
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    sandbox_dir = os.path.join(workspace_dir, "agenthub_export", test_conv_id)
    
    # 0. Cleanup old sandbox folders
    if os.path.exists(sandbox_dir):
        shutil.rmtree(sandbox_dir)
    os.makedirs(sandbox_dir, exist_ok=True)

    # 1. Verify Built-in System Server registration
    print("[Step 1] Verifying SystemServer registration in MCPManager...")
    assert "SystemServer" in mcp_manager.servers
    print("  SUCCESS: SystemServer successfully registered globally.")

    # 2. Verify listing tools
    print("\n[Step 2] Querying available MCP tools from registered servers...")
    tools = await mcp_manager.get_all_tools()
    assert len(tools) > 0
    namespaced_tool_names = [t["name"] for t in tools]
    print(f"  Available namespaced tools: {namespaced_tool_names}")
    assert "SystemServer__workspace_list_dir" in namespaced_tool_names
    assert "SystemServer__workspace_write_file" in namespaced_tool_names
    assert "SystemServer__workspace_read_file" in namespaced_tool_names
    assert "SystemServer__workspace_run_command" in namespaced_tool_names
    print("  SUCCESS: Discovered tools from system MCP server match requirements.")

    # 3. Test workspace_write_file
    print("\n[Step 3] Testing workspace_write_file tool invocation...")
    write_args = {
        "path": "hello_mcp.txt",
        "content": "Hello standard Model Context Protocol native tools integration!"
    }
    write_res = await mcp_manager.execute_tool("SystemServer__workspace_write_file", write_args, conversation_id=test_conv_id)
    assert not write_res.get("isError", False)
    content_list = write_res.get("content", [])
    assert len(content_list) > 0
    print(f"  Tool execution output: {content_list[0]['text']}")
    
    # Verify file physically written
    physical_file = os.path.join(sandbox_dir, "hello_mcp.txt")
    assert os.path.exists(physical_file)
    with open(physical_file, "r", encoding="utf-8") as f:
        read_back = f.read()
    assert read_back == write_args["content"]
    print("  SUCCESS: Tool workspace_write_file successfully wrote the sandboxed file physically.")

    # 4. Test workspace_read_file
    print("\n[Step 4] Testing workspace_read_file tool invocation...")
    read_args = {
        "path": "hello_mcp.txt"
    }
    read_res = await mcp_manager.execute_tool("SystemServer__workspace_read_file", read_args, conversation_id=test_conv_id)
    assert not read_res.get("isError", False)
    read_content = read_res.get("content", [])
    assert len(read_content) > 0
    assert read_content[0]["text"] == write_args["content"]
    print(f"  Tool execution read-back: {read_content[0]['text']}")
    print("  SUCCESS: Tool workspace_read_file successfully read the correct sandboxed file.")

    # 5. Test workspace_list_dir
    print("\n[Step 5] Testing workspace_list_dir tool invocation...")
    list_args = {
        "path": ""
    }
    list_res = await mcp_manager.execute_tool("SystemServer__workspace_list_dir", list_args, conversation_id=test_conv_id)
    assert not list_res.get("isError", False)
    list_content = list_res.get("content", [])
    assert len(list_content) > 0
    parsed_items = json.loads(list_content[0]["text"])
    item_names = [i["name"] for i in parsed_items]
    print(f"  Sandboxed items found: {item_names}")
    assert "hello_mcp.txt" in item_names
    print("  SUCCESS: Tool workspace_list_dir successfully listed the directory.")

    # 6. Test workspace_run_command (terminal execution sandbox)
    print("\n[Step 6] Testing workspace_run_command execution inside sandboxed workspace...")
    # Run echo command
    cmd_args = {
        "command": "echo Hello from Sandboxed CLI"
    }
    cmd_res = await mcp_manager.execute_tool("SystemServer__workspace_run_command", cmd_args, conversation_id=test_conv_id)
    assert not cmd_res.get("isError", False)
    cmd_content = cmd_res.get("content", [])
    assert len(cmd_content) > 0
    print("  Terminal execution log block:")
    print("  ------------------------------------------------")
    print(cmd_content[0]["text"].strip())
    print("  ------------------------------------------------")
    assert "Hello from Sandboxed CLI" in cmd_content[0]["text"]
    print("  SUCCESS: Tool workspace_run_command executed successfully and returned stdout.")

    # Cleanup sandbox files
    shutil.rmtree(sandbox_dir)

    print("\n====================================================")
    print("🎉 SUCCESS: Plan D Model Context Protocol integration regression suite finished with 100% PASS!")
    print("====================================================")

if __name__ == "__main__":
    asyncio.run(run_mcp_testing())
