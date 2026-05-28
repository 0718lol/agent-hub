import asyncio
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, ANY

# Setup import path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Reconfigure stdout to support utf-8 on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.core.database import (
    init_db, save_cron_task, get_cron_tasks, get_due_cron_tasks,
    update_cron_task_run_time, update_cron_task_status, delete_cron_task,
    get_messages, clear_messages
)
from app.services.daemon_scheduler import daemon_scheduler

async def run_daemon_testing():
    print("====================================================")
    print("[START] Plan G: Always-on Offline Autonomous Daemon Regression Test")
    print("====================================================\n")

    # Step 0: Initialize database
    print("[Step 0] Initializing database schemas and clearing state...")
    init_db()
    
    test_conv_id = "conv_test_daemon_milestone"
    test_task_id = "task_test_daemon_123"
    
    # Clean any existing test tasks
    delete_cron_task(test_task_id)
    
    # Step 1: Test Database CRUD operations for Cron Tasks
    print("\n[Step 1] Testing Cron Tasks SQLite CRUD Operations...")
    now = datetime.utcnow()
    next_run_str = (now + timedelta(seconds=60)).strftime("%Y-%m-%d %H:%M:%S")
    
    save_cron_task(
        task_id=test_task_id,
        conversation_id=test_conv_id,
        agent_id="agent_pm",
        task_prompt="Run security checks and refactor workspace code.",
        interval_seconds=60,
        status="active",
        last_run=None,
        next_run=next_run_str
    )
    
    # Fetch task and assert
    tasks = get_cron_tasks(test_conv_id)
    assert len(tasks) == 1
    assert tasks[0]["id"] == test_task_id
    assert tasks[0]["agent_id"] == "agent_pm"
    assert tasks[0]["status"] == "active"
    assert tasks[0]["interval_seconds"] == 60
    print("  SUCCESS: Cron task successfully created and queried from SQLite.")

    # Step 2: Test Fetching Due Tasks
    print("\n[Step 2] Testing get_due_cron_tasks query filtering...")
    # Current time is past the scheduled run time
    past_time = (now + timedelta(seconds=120)).strftime("%Y-%m-%d %H:%M:%S")
    due_tasks = get_due_cron_tasks(past_time)
    assert any(t["id"] == test_task_id for t in due_tasks)
    print("  SUCCESS: Due task successfully picked up by next_run filter.")

    # Test toggling/pausing task
    update_cron_task_status(test_task_id, "paused")
    due_tasks_paused = get_due_cron_tasks(past_time)
    assert not any(t["id"] == test_task_id for t in due_tasks_paused)
    print("  SUCCESS: Paused cron task correctly filtered out from due list.")

    # Re-activate task
    update_cron_task_status(test_task_id, "active")

    # Step 3: Test Dynamic Task Running & Execution Pipeline Flow
    print("\n[Step 3] Simulating Background Autonomous Daemon execution loop...")
    
    # Mock _stream_agent_reply to avoid real external model/network calls
    mock_reply = AsyncMock(return_value=(["agent_pm"], "Autonomous security audits completed successfully. No vulnerabilities found."))
    
    with patch("app.main._stream_agent_reply", mock_reply):
        # We need agent_pm in main.AGENTS, which is initialized at startup. Let's verify AGENTS has it.
        from app.main import AGENTS
        assert "agent_pm" in AGENTS
        
        print("  Triggering daemon worker task non-blockingly...")
        task_obj = {
            "id": test_task_id,
            "conversation_id": test_conv_id,
            "agent_id": "agent_pm",
            "task_prompt": "Run security checks and refactor workspace code.",
            "interval_seconds": 60
        }
        
        # Execute the background worker directly
        await daemon_scheduler._run_task(task_obj)
        
        # Verify the mock stream reply was invoked correctly
        mock_reply.assert_called_once_with(
            conversation_id=test_conv_id,
            agent=AGENTS["agent_pm"],
            user_text="Run security checks and refactor workspace code.",
            stop_event=ANY
        )
        print("  SUCCESS: Background agent stream reply called correctly.")
        
        # Verify database fields updated after run
        updated_tasks = get_cron_tasks(test_conv_id)
        assert len(updated_tasks) == 1
        assert updated_tasks[0]["status"] == "active"
        assert updated_tasks[0]["last_run"] is not None
        assert updated_tasks[0]["next_run"] is not None
        
        # Check next run is properly set in future
        last_dt = datetime.strptime(updated_tasks[0]["last_run"], "%Y-%m-%d %H:%M:%S")
        next_dt = datetime.strptime(updated_tasks[0]["next_run"], "%Y-%m-%d %H:%M:%S")
        assert (next_dt - last_dt).total_seconds() == 60
        print("  SUCCESS: Cron task last_run, next_run schedules updated.")

    # Step 4: Test Autonomous Error-Handling & DB Fallback logger
    print("\n[Step 4] Testing task execution failure fallback logger...")
    
    # Mock stream reply to raise an exception
    mock_error_reply = AsyncMock(side_effect=RuntimeError("Sandbox compiler timeout!"))
    
    # Clear conversation message history for a clean slate
    clear_messages(test_conv_id)
    
    with patch("app.main._stream_agent_reply", mock_error_reply):
        print("  Running task with simulated runtime crash...")
        await daemon_scheduler._run_task(task_obj)
        
        # Verify status reset to active
        updated_tasks = get_cron_tasks(test_conv_id)
        assert updated_tasks[0]["status"] == "active"
        
        # Verify error message was saved in SQLite conversation history
        messages = get_messages(test_conv_id)
        assert len(messages) > 0
        last_msg = messages[-1]
        text_content = ""
        if isinstance(last_msg, dict):
            if "content" in last_msg and isinstance(last_msg["content"], dict):
                text_content = last_msg["content"].get("text", "")
            else:
                text_content = last_msg.get("text", "")
        else:
            text_content = str(last_msg)
        
        print(f"  Captured message in history: {text_content}")
        assert "[后台自治运行异常]" in str(text_content)
        assert "RuntimeError" in str(text_content)
        print("  SUCCESS: Autonomous error recovery and SQLite telemetry logger verified!")

    # Step 5: Test Polling Lifecycle Controls (start / stop)
    print("\n[Step 5] Verifying non-blocking scheduler lifecycle control...")
    assert not daemon_scheduler._running
    daemon_scheduler.start()
    assert daemon_scheduler._running
    assert daemon_scheduler._task is not None
    print("  SUCCESS: Daemon background loop thread-like coroutine initialized successfully.")
    
    await daemon_scheduler.stop()
    assert not daemon_scheduler._running
    print("  SUCCESS: Daemon background loop stopped cleanly.")

    # Cleanup test tasks
    delete_cron_task(test_task_id)
    
    print("\n====================================================")
    print("🎉 SUCCESS: Plan G Autonomous Daemon Scheduler regression suite passed with 100% PASS!")
    print("====================================================")

if __name__ == "__main__":
    asyncio.run(run_daemon_testing())
