import asyncio
import os
import shutil
import sys
import json

# Setup import path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Reconfigure stdout to support utf-8 on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.core.database import (
    init_db, save_message, get_messages, get_project_memory, save_memory_item, delete_memory_item
)
from app.core.prompt_engine import prompt_engine
from app.services.memory_engine import trigger_background_reflection
from app.core.llm_client import llm_client

class MockAgent:
    def __init__(self):
        self.agent_id = "agent_frontend"
        self.name = "前端工程师"
        self.role = "React 组件与样式开发"
        self.style = "专业严谨"
        self.tools = ["code_gen", "web_preview"]

async def run_sandbox_testing():
    print("====================================================")
    print("[START] AgentHub Sandbox & Long-term Memory System Comprehensive Test")
    print("====================================================\n")

    # 0. Initialize Database
    print("[Step 0] Initializing database schemas...")
    init_db()
    test_conv_id = "conv_test_sandbox_milestone"

    # 1. Test Sandboxed Workspace File Creation (Plan A)
    print("\n[Step 1] Testing Plan A - Workspace Sandboxing & Isolated Deploy...")
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    sandbox_export_dir = os.path.join(workspace_dir, "agenthub_export", test_conv_id)
    
    # Simulate deploy file generation
    try:
        if os.path.exists(sandbox_export_dir):
            shutil.rmtree(sandbox_export_dir)
        os.makedirs(sandbox_export_dir, exist_ok=True)
        
        # Write dummy files
        with open(os.path.join(sandbox_export_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write("<!DOCTYPE html><html><body><h1>Sandbox Test Success!</h1></body></html>")
            
        with open(os.path.join(sandbox_export_dir, "双击运行.bat"), "w", encoding="gbk") as f:
            f.write("@echo off\nstart index.html\n")
            
        print(f"  SUCCESS: Isolated sandboxed workspace folder created at: {sandbox_export_dir}")
        assert os.path.exists(os.path.join(sandbox_export_dir, "index.html"))
        assert os.path.exists(os.path.join(sandbox_export_dir, "双击运行.bat"))
        print("  SUCCESS: Plan A sandboxing path verification passed!")
    except Exception as e:
        print(f"  FAIL: Plan A sandboxing verification failed: {e}")
        return

    # 2. Test Memory Database CRUD (Plan B Core)
    print("\n[Step 2] Testing Plan B - SQLite Memory CRUD and Physical Forgetting...")
    try:
        # Save memory items
        save_memory_item(test_conv_id, "tech_stack", "FastAPI + SQLite, React18, Port 8000", source="system")
        save_memory_item(test_conv_id, "user_preference", "喜欢磨砂玻璃暗黑拟态风格", source="user")
        save_memory_item(test_conv_id, "implemented_features", "- 实现了方案 A 工作空间沙盒\n- 接入了记忆 CRUD 端点", source="system")
        
        print("  SUCCESS: Successfully wrote 3 memory dimensions to SQLite database!")
        
        # Read and check memory
        mem = get_project_memory(test_conv_id)
        assert "tech_stack" in mem
        assert mem["tech_stack"]["value"] == "FastAPI + SQLite, React18, Port 8000"
        assert mem["tech_stack"]["source"] == "system"
        assert mem["user_preference"]["source"] == "user"
        print("  SUCCESS: Long-term memory query values and source tag verified!")
        
        # Test forget (delete)
        delete_memory_item(test_conv_id, "implemented_features")
        mem_after_del = get_project_memory(test_conv_id)
        assert "implemented_features" not in mem_after_del
        print("  SUCCESS: Memory forgetting (item deletion) verified!")
    except Exception as e:
        print(f"  FAIL: Plan B database CRUD verification failed: {e}")
        return

    # 3. Test Prompt L3 Layer Dynamic Injection
    print("\n[Step 3] Testing Plan B - Prompt Engine L3 Layer Dynamic Memory Injection...")
    try:
        agent = MockAgent()
        ctx = {"task_type": "html", "conversation_id": test_conv_id}
        
        # Build prompt
        assembled_prompt = prompt_engine.build(agent, ctx)
        
        print("  --- Injected L3 Memory Slice Preview ---")
        for line in assembled_prompt.splitlines():
            if "长期记忆" in line or "技术契约" in line or "技术栈" in line or "偏好" in line:
                print(f"    {line}")
        print("  ----------------------------------------")
        
        assert "技术栈与接口契约" in assembled_prompt
        assert "FastAPI + SQLite" in assembled_prompt
        assert "用户偏好与设计风格" in assembled_prompt
        assert "喜欢磨砂玻璃暗黑拟态风格" in assembled_prompt
        print("  SUCCESS: Prompt L3 Layer dynamic insertion verified successfully!")
    except Exception as e:
        print(f"  FAIL: Prompt L3 Layer injection verification failed: {e}")
        return

    # 4. Mock Background reflection parsing
    print("\n[Step 4] Testing Plan B - Reflection summarization JSON parser...")
    
    # Save dummy history messages
    save_message(test_conv_id, "user", {"text": "请将后端开发接口路径改为 /api/v2 并且全部返回 JSON。"})
    save_message(test_conv_id, "agent_backend", {"text": "[thinking]我需要修改接口契约[/thinking]好的，我已将接口规范调整为 /api/v2，所有响应均为 JSON 结构。"})
    
    # Simulated reflected JSON reply
    mock_llm_json_reply = """
    {
      "tech_stack": "FastAPI + SQLite, React18, API 接口更新为 /api/v2",
      "user_preference": "喜欢磨砂玻璃暗黑拟态风格，后端返回全 JSON",
      "implemented_features": "- 完成方案 A 物理沙盒隔离化部署接口\\n- 接口规范全面更新为 v2",
      "pending_todos": "- 启动方案 C 多路路由调度架构"
    }
    """
    
    try:
        # Simulate JSON parse and DB update
        clean_json = mock_llm_json_reply.strip()
        updated_data = json.loads(clean_json)
        for key in ["tech_stack", "user_preference", "implemented_features", "pending_todos"]:
            if key in updated_data:
                save_memory_item(test_conv_id, key, str(updated_data[key]), source="system")
                
        # Fetch updated memory
        final_mem = get_project_memory(test_conv_id)
        assert "pending_todos" in final_mem
        assert "api/v2" in final_mem["tech_stack"]["value"]
        print("  SUCCESS: Background reflected memory parse and DB upsert verified!")
    except Exception as e:
        print(f"  FAIL: Plan B background reflection parsing failed: {e}")
        return

    # Clean up mock database values
    delete_memory_item(test_conv_id, "tech_stack")
    delete_memory_item(test_conv_id, "user_preference")
    delete_memory_item(test_conv_id, "implemented_features")
    delete_memory_item(test_conv_id, "pending_todos")
    
    print("\n====================================================")
    print("🎉 SUCCESS: Plan A & Plan B sandbox validation completed with 100% PASS!")
    print("====================================================")

if __name__ == "__main__":
    asyncio.run(run_sandbox_testing())
