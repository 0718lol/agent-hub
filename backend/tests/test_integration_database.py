"""
Integration tests for core database CRUD operations.

Tests the full lifecycle (create -> query -> update -> delete) of each
major entity using an in-memory SQLite database.
"""
import json
import os

import pytest
from sqlalchemy import event, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

# ---------------------------------------------------------------------------
# Fixtures: isolated in-memory engine for integration tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_engine(monkeypatch):
    """
    Replace the global ``engine`` with a fresh in-memory SQLite engine so
    every test starts with a clean, empty database.

    We also disable WAL pragmas since :memory: doesn't support them
    the same way file-backed SQLite does.
    """
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create all tables
    from app.core.models import (
        Artifact,
        Conversation,
        CronTask,
        CustomAgent,
        KnowledgeDoc,
        Message,
        PendingHil,
        ProjectEventStream,
        ProjectMemory,
        UploadedFile,
    )

    SQLModel.metadata.create_all(test_engine)

    # Patch engine everywhere it is imported
    import app.core._engine as _engine_mod
    import app.core.crud as crud_mod

    monkeypatch.setattr(_engine_mod, "engine", test_engine)
    monkeypatch.setattr(crud_mod, "engine", test_engine)

    yield test_engine

    SQLModel.metadata.drop_all(test_engine)


# ---------------------------------------------------------------------------
# Helper to seed prerequisite conversation rows (FK targets)
# ---------------------------------------------------------------------------

def _seed_conversation(session, conv_id: str, conv_type: str = "single",
                       name: str = "test", avatar: str = "\U0001f916"):
    """Insert a conversation row so that FK-dependent tables can reference it."""
    session.execute(
        text(
            "INSERT OR IGNORE INTO conversations (id, type, name, avatar, created_at) "
            "VALUES (:id, :type, :name, :avatar, datetime('now'))"
        ),
        {"id": conv_id, "type": conv_type, "name": name, "avatar": avatar},
    )
    session.commit()


# ===================================================================
# Conversation tests
# ===================================================================

class TestConversationLifecycle:

    def test_create_and_list(self):
        """创建会话后能从列表中查到。"""
        from app.core.crud import create_conversation, get_conversations

        create_conversation("conv_lc_001", "single", "生命周期测试", "\U0001f916")

        convs = get_conversations()
        assert any(c["id"] == "conv_lc_001" for c in convs)

    def test_create_is_idempotent(self):
        """重复创建同一 conversation 不会报错。"""
        from app.core.crud import create_conversation, get_conversations

        create_conversation("conv_idem_001", "single", "幂等测试", "\U0001f916")
        create_conversation("conv_idem_001", "single", "幂等测试", "\U0001f916")  # no-op

        convs = get_conversations()
        matching = [c for c in convs if c["id"] == "conv_idem_001"]
        assert len(matching) == 1

    def test_conversation_has_expected_fields(self):
        """创建的会话包含所有必要字段。"""
        from app.core.crud import create_conversation, get_conversations

        create_conversation(
            "conv_fields_001", "group", "字段测试", "\U0001f680",
            agent_id="agent_pm", agents=["agent_pm", "agent_fe"], preview="hello"
        )

        convs = get_conversations()
        conv = next(c for c in convs if c["id"] == "conv_fields_001")
        assert conv["type"] == "group"
        assert conv["name"] == "字段测试"
        assert conv["avatar"] == "\U0001f680"
        assert conv["agent_id"] == "agent_pm"
        assert conv["agents"] == ["agent_pm", "agent_fe"]
        assert conv["preview"] == "hello"


# ===================================================================
# Message tests
# ===================================================================

class TestMessageSaveAndRetrieve:

    def test_save_and_retrieve(self):
        """保存消息后能按 conversation_id 正确读取。"""
        from app.core.crud import create_conversation, get_messages, save_message

        # FK: conversation must exist first
        create_conversation("conv_msg_001", "single", "消息测试", "\U0001f916")

        save_message("conv_msg_001", "user", {"text": "hello"}, streaming=False)
        save_message("conv_msg_001", "agent_pm", {"text": "hi there"}, streaming=False)

        messages = get_messages("conv_msg_001")
        assert len(messages) == 2
        assert messages[0]["sender"] == "user"
        assert messages[0]["content"] == {"text": "hello"}
        assert messages[1]["sender"] == "agent_pm"
        assert messages[1]["content"] == {"text": "hi there"}

    def test_messages_ordered_by_id(self):
        """消息按 id 升序排列。"""
        from app.core.crud import create_conversation, get_messages, save_message

        create_conversation("conv_msg_order", "single", "排序测试", "\U0001f916")

        save_message("conv_msg_order", "user", {"text": "first"})
        save_message("conv_msg_order", "agent_pm", {"text": "second"})
        save_message("conv_msg_order", "user", {"text": "third"})

        messages = get_messages("conv_msg_order")
        ids = [m["id"] for m in messages]
        assert ids == sorted(ids)

    def test_limit_parameter(self):
        """limit 参数限制返回数量。"""
        from app.core.crud import create_conversation, get_messages, save_message

        create_conversation("conv_msg_limit", "single", "限制测试", "\U0001f916")

        for i in range(10):
            save_message("conv_msg_limit", "user", {"text": f"msg {i}"})

        messages = get_messages("conv_msg_limit", limit=3)
        assert len(messages) == 3

    def test_empty_conversation_returns_empty_list(self):
        """无消息的会话返回空列表。"""
        from app.core.crud import create_conversation, get_messages

        create_conversation("conv_empty", "single", "空会话", "\U0001f916")

        messages = get_messages("conv_empty")
        assert messages == []

    def test_clear_messages(self):
        """clear_messages 清除指定会话的所有消息。"""
        from app.core.crud import (
            clear_messages,
            create_conversation,
            get_messages,
            save_message,
        )

        create_conversation("conv_clear", "single", "清除测试", "\U0001f916")
        save_message("conv_clear", "user", {"text": "to be cleared"})
        save_message("conv_clear", "agent_pm", {"text": "also cleared"})

        clear_messages("conv_clear")
        messages = get_messages("conv_clear")
        assert messages == []

    def test_streaming_flag(self):
        """streaming 字段正确序列化/反序列化。"""
        from app.core.crud import create_conversation, get_messages, save_message

        create_conversation("conv_stream", "single", "流式测试", "\U0001f916")

        save_message("conv_stream", "user", {"text": "test"}, streaming=True)
        save_message("conv_stream", "agent_pm", {"text": "test2"}, streaming=False)

        messages = get_messages("conv_stream")
        assert messages[0]["streaming"] is True
        assert messages[1]["streaming"] is False


# ===================================================================
# Custom Agent tests
# ===================================================================

class TestCustomAgentPersistence:

    def test_save_and_list(self):
        """保存自定义 Agent 后能从列表中查到。"""
        from app.core.crud import get_custom_agents, save_custom_agent

        save_custom_agent(
            "agent_test_001", "测试Agent", "\U0001f916",
            "测试角色", "友好", "你是测试Agent", ["code_gen"]
        )

        agents = get_custom_agents()
        agent = next((a for a in agents if a["agent_id"] == "agent_test_001"), None)
        assert agent is not None
        assert agent["name"] == "测试Agent"
        assert agent["role"] == "测试角色"
        assert agent["style"] == "友好"
        assert agent["system_prompt"] == "你是测试Agent"
        assert agent["tools"] == ["code_gen"]
        assert agent["custom"] is True

    def test_delete_agent(self):
        """删除自定义 Agent 后不再出现。"""
        from app.core.crud import (
            delete_custom_agent,
            get_custom_agents,
            save_custom_agent,
        )

        save_custom_agent(
            "agent_del_001", "删除测试", "\U0001f916",
            "角色", "风格", "prompt", ["tool_a"]
        )
        assert any(a["agent_id"] == "agent_del_001" for a in get_custom_agents())

        delete_custom_agent("agent_del_001")
        assert not any(a["agent_id"] == "agent_del_001" for a in get_custom_agents())

    def test_save_custom_agent_upserts(self):
        """重复保存同一 agent_id 会更新而非报错。"""
        from app.core.crud import get_custom_agents, save_custom_agent

        save_custom_agent(
            "agent_upsert", "旧名", "\U0001f916",
            "旧角色", "旧风格", "旧prompt", ["tool_old"]
        )
        save_custom_agent(
            "agent_upsert", "新名", "\U0001f680",
            "新角色", "新风格", "新prompt", ["tool_new"]
        )

        agents = get_custom_agents()
        matching = [a for a in agents if a["agent_id"] == "agent_upsert"]
        assert len(matching) == 1
        assert matching[0]["name"] == "新名"
        assert matching[0]["tools"] == ["tool_new"]


# ===================================================================
# Cron Task tests
# ===================================================================

class TestCronTaskLifecycle:

    def test_create_query_update_delete(self):
        """定时任务的完整生命周期：创建 -> 查询 -> 状态更新 -> 删除。"""
        # FK: conversation must exist
        from app.core.crud import (
            create_conversation,
            delete_cron_task,
            get_cron_tasks,
            save_cron_task,
            update_cron_task_status,
        )
        create_conversation("conv_cron_001", "single", "定时任务测试", "\U0001f916")

        # Create
        save_cron_task(
            task_id="task_001",
            conversation_id="conv_cron_001",
            agent_id="agent_pm",
            task_prompt="执行每日报告",
            interval_seconds=3600,
        )

        tasks = get_cron_tasks()
        task = next((t for t in tasks if t["id"] == "task_001"), None)
        assert task is not None
        assert task["agent_id"] == "agent_pm"
        assert task["interval_seconds"] == 3600
        assert task["status"] == "active"

        # Update status
        update_cron_task_status("task_001", "running")
        tasks = get_cron_tasks()
        task = next(t for t in tasks if t["id"] == "task_001")
        assert task["status"] == "running"

        # Delete
        delete_cron_task("task_001")
        tasks = get_cron_tasks()
        assert not any(t["id"] == "task_001" for t in tasks)

    def test_get_cron_tasks_by_conversation(self):
        """按 conversation_id 过滤定时任务。"""
        from app.core.crud import create_conversation, get_cron_tasks, save_cron_task
        create_conversation("conv_cron_filter_a", "single", "A", "\U0001f916")
        create_conversation("conv_cron_filter_b", "single", "B", "\U0001f916")

        save_cron_task("task_a1", "conv_cron_filter_a", "agent_pm", "task a1", 600)
        save_cron_task("task_b1", "conv_cron_filter_b", "agent_pm", "task b1", 1200)

        tasks_a = get_cron_tasks(conversation_id="conv_cron_filter_a")
        assert len(tasks_a) == 1
        assert tasks_a[0]["id"] == "task_a1"

    def test_update_cron_task_run_time(self):
        """更新定时任务的运行时间。"""
        from app.core.crud import (
            create_conversation,
            get_cron_tasks,
            save_cron_task,
            update_cron_task_run_time,
        )
        create_conversation("conv_cron_rt", "single", "运行时间测试", "\U0001f916")

        save_cron_task("task_rt", "conv_cron_rt", "agent_pm", "test", 3600)

        update_cron_task_run_time("task_rt", "2026-01-01T09:00:00", "2026-01-02T09:00:00")

        tasks = get_cron_tasks()
        task = next(t for t in tasks if t["id"] == "task_rt")
        assert task["last_run"] == "2026-01-01T09:00:00"
        assert task["next_run"] == "2026-01-02T09:00:00"

    def test_recover_running_tasks_after_restart(self):
        from app.core.crud import (
            create_conversation,
            get_cron_tasks,
            recover_running_cron_tasks,
            save_cron_task,
        )

        create_conversation("conv_cron_recover", "single", "恢复任务", "🤖")
        save_cron_task(
            "task_recover", "conv_cron_recover", "agent_pm", "resume", 600,
            status="running",
        )

        assert recover_running_cron_tasks("2026-07-15 00:00:00") >= 1
        task = next(task for task in get_cron_tasks() if task["id"] == "task_recover")
        assert task["status"] == "active"
        assert task["next_run"] == "2026-07-15 00:00:00"


# ===================================================================
# Knowledge Doc tests
# ===================================================================

class TestKnowledgeDocLifecycle:

    def test_save_and_list(self):
        """保存知识库文档后能查到。"""
        from app.core.crud import get_knowledge_docs, save_knowledge_doc

        save_knowledge_doc(
            doc_id="doc_001", filename="测试文档.pdf",
            file_path="/tmp/test.pdf", content_type="application/pdf",
            chunk_count=10, char_count=5000,
        )

        docs = get_knowledge_docs()
        doc = next((d for d in docs if d["id"] == "doc_001"), None)
        assert doc is not None
        assert doc["filename"] == "测试文档.pdf"
        assert doc["chunk_count"] == 10
        assert doc["char_count"] == 5000
        assert doc["status"] == "ready"

    def test_delete_knowledge_doc(self):
        """删除知识库文档后不再出现。"""
        from app.core.crud import (
            delete_knowledge_doc,
            get_knowledge_docs,
            save_knowledge_doc,
        )

        save_knowledge_doc(doc_id="doc_del_001", filename="待删文档.txt")
        assert any(d["id"] == "doc_del_001" for d in get_knowledge_docs())

        delete_knowledge_doc("doc_del_001")
        assert not any(d["id"] == "doc_del_001" for d in get_knowledge_docs())


# ===================================================================
# Artifact tests
# ===================================================================

class TestArtifactSaveAndRetrieve:

    def test_save_and_retrieve(self):
        """保存代码工件后能正确查询。"""
        from app.core.crud import create_conversation, get_artifacts, save_artifact
        create_conversation("conv_art_001", "single", "工件测试", "\U0001f916")

        save_artifact("conv_art_001", "agent_frontend", "html", "<h1>Hello</h1>", "test.html")

        artifacts = get_artifacts("conv_art_001")
        assert len(artifacts) >= 1
        assert artifacts[0]["language"] == "html"
        assert artifacts[0]["code"] == "<h1>Hello</h1>"
        assert artifacts[0]["name"] == "test.html"

    def test_artifact_name_auto_generation(self):
        """未指定 name 时自动生成。"""
        from app.core.crud import create_conversation, get_artifacts, save_artifact
        create_conversation("conv_art_auto", "single", "自动命名", "\U0001f916")

        save_artifact("conv_art_auto", "agent_frontend", "html",
                       "<html><head><title>MyPage</title></head></html>")

        artifacts = get_artifacts("conv_art_auto")
        assert artifacts[0]["name"] == "MyPage.html"

    def test_artifact_grouped(self):
        """get_artifacts_grouped 按 name 分组。"""
        from app.core.crud import create_conversation, get_artifacts_grouped, save_artifact
        create_conversation("conv_art_grp", "single", "分组测试", "\U0001f916")

        # Two versions of the same artifact name
        save_artifact("conv_art_grp", "agent_fe", "html", "<h1>v1</h1>", "index.html")
        save_artifact("conv_art_grp", "agent_fe", "html", "<h1>v2</h1>", "index.html")

        grouped = get_artifacts_grouped("conv_art_grp")
        assert len(grouped) == 1
        assert grouped[0]["total_versions"] == 2
        assert grouped[0]["name"] == "index.html"


# ===================================================================
# Search (FTS5 / LIKE fallback) tests
# ===================================================================

class TestSearchMessages:

    def test_search_finds_matching_messages(self):
        """search_messages 能找到匹配的消息。"""
        from app.core.crud import create_conversation, save_message, search_messages
        create_conversation("conv_search_001", "single", "搜索测试", "\U0001f916")

        save_message("conv_search_001", "user", {"text": "Python is a great programming language"})
        save_message("conv_search_001", "agent_pm", {"text": "I agree, Python is versatile"})
        save_message("conv_search_001", "user", {"text": "Hello world"})

        results = search_messages("Python")
        assert len(results) >= 2

    def test_search_with_conversation_filter(self):
        """按 conversation_id 过滤搜索结果。"""
        from app.core.crud import create_conversation, save_message, search_messages
        create_conversation("conv_search_a", "single", "搜索A", "\U0001f916")
        create_conversation("conv_search_b", "single", "搜索B", "\U0001f916")

        save_message("conv_search_a", "user", {"text": "Python rocks"})
        save_message("conv_search_b", "user", {"text": "Python also here"})

        results = search_messages("Python", conversation_id="conv_search_a")
        assert len(results) == 1
        assert results[0]["conversation_id"] == "conv_search_a"

    def test_search_no_results(self):
        """搜索不存在的关键词返回空列表。"""
        from app.core.crud import create_conversation, save_message, search_messages
        create_conversation("conv_search_empty", "single", "空搜索", "\U0001f916")

        save_message("conv_search_empty", "user", {"text": "hello"})

        results = search_messages("xyznonexistent12345")
        assert len(results) == 0


# ===================================================================
# JSON fallback for non-JSON content
# ===================================================================

class TestJsonFallback:

    def test_non_json_content_does_not_crash(self):
        """非 JSON 内容应有 fallback 而不是崩溃。"""
        from app.core._engine import engine

        # Create parent conversation via FK
        from app.core.crud import create_conversation, get_messages
        create_conversation("conv_json_test", "single", "JSON测试", "\U0001f916")

        # Insert raw non-JSON content directly (simulates legacy data)
        with Session(engine) as session:
            session.execute(
                text(
                    "INSERT INTO messages (conversation_id, sender, content, streaming, created_at) "
                    "VALUES (:conv_id, :sender, :content, :streaming, datetime('now'))"
                ),
                {
                    "conv_id": "conv_json_test",
                    "sender": "user",
                    "content": "plain text not json",
                    "streaming": 0,
                },
            )
            session.commit()

        # Reading should NOT crash; should return {"text": "plain text not json"}
        messages = get_messages("conv_json_test")
        assert len(messages) >= 1
        assert messages[0]["content"]["text"] == "plain text not json"

    def test_valid_json_content_parsed_correctly(self):
        """合法 JSON 内容能被正确解析。"""
        from app.core.crud import create_conversation, get_messages, save_message
        create_conversation("conv_json_ok", "single", "JSON正常", "\U0001f916")

        save_message("conv_json_ok", "user", {"text": "hello", "extra": [1, 2, 3]})

        messages = get_messages("conv_json_ok")
        assert messages[0]["content"]["text"] == "hello"
        assert messages[0]["content"]["extra"] == [1, 2, 3]


# ===================================================================
# Project Memory tests
# ===================================================================

class TestProjectMemory:

    def test_save_and_get(self):
        """保存和读取项目记忆。"""
        from app.core.crud import create_conversation, get_project_memory, save_memory_item
        create_conversation("conv_mem_001", "single", "记忆测试", "\U0001f916")

        save_memory_item("conv_mem_001", "project_name", "AgentHub", source="agent")
        save_memory_item("conv_mem_001", "language", "Python")

        memory = get_project_memory("conv_mem_001")
        assert "project_name" in memory
        assert memory["project_name"]["value"] == "AgentHub"
        assert memory["project_name"]["source"] == "agent"
        assert memory["language"]["value"] == "Python"

    def test_upsert_updates_existing_key(self):
        """相同 conversation_id + key 会更新值而非插入新行。"""
        from app.core.crud import create_conversation, get_project_memory, save_memory_item
        create_conversation("conv_mem_up", "single", "记忆更新", "\U0001f916")

        save_memory_item("conv_mem_up", "key1", "old_value")
        save_memory_item("conv_mem_up", "key1", "new_value")

        memory = get_project_memory("conv_mem_up")
        assert memory["key1"]["value"] == "new_value"

    def test_delete_memory_item(self):
        """删除指定记忆项。"""
        from app.core.crud import (
            create_conversation,
            delete_memory_item,
            get_project_memory,
            save_memory_item,
        )
        create_conversation("conv_mem_del", "single", "记忆删除", "\U0001f916")

        save_memory_item("conv_mem_del", "to_delete", "value")
        delete_memory_item("conv_mem_del", "to_delete")

        memory = get_project_memory("conv_mem_del")
        assert "to_delete" not in memory


# ===================================================================
# HIL Checkpoint tests
# ===================================================================

class TestHilCheckpoint:

    def test_save_get_resolve_delete(self):
        """HIL 检查点的完整生命周期。"""
        from app.core.crud import (
            create_conversation,
            delete_hil_checkpoint,
            get_pending_hil_checkpoint,
            resolve_hil_checkpoint,
            save_hil_checkpoint,
        )
        create_conversation("conv_hil_001", "single", "HIL测试", "\U0001f916")

        # Save
        save_hil_checkpoint(
            conversation_id="conv_hil_001",
            current_node="review",
            next_node="execute",
            state_data={"plan": "deploy"},
            question="确认部署?",
            options=["是", "否"],
            original_prompt="请部署应用",
        )

        # Get
        checkpoint = get_pending_hil_checkpoint("conv_hil_001")
        assert checkpoint is not None
        assert checkpoint["question"] == "确认部署?"
        assert checkpoint["options"] == ["是", "否"]
        assert checkpoint["state_data"]["plan"] == "deploy"
        assert checkpoint["status"] == "pending"

        # Resolve
        resolve_hil_checkpoint("conv_hil_001", "是")
        checkpoint = get_pending_hil_checkpoint("conv_hil_001")
        assert checkpoint is None  # no longer "pending"

        # Delete
        delete_hil_checkpoint("conv_hil_001")


# ===================================================================
# Event Stream tests
# ===================================================================

class TestEventStream:

    def test_save_and_get_events(self):
        """保存和读取事件流。"""
        from app.core.crud import create_conversation, get_event_items, save_event_item
        create_conversation("conv_evt_001", "single", "事件测试", "\U0001f916")

        save_event_item("conv_evt_001", "message_sent", 1700000000.0, '{"from": "user"}')
        save_event_item("conv_evt_001", "agent_reply", 1700000001.0, '{"from": "agent"}')

        events = get_event_items("conv_evt_001")
        assert len(events) == 2
        assert events[0]["event_type"] == "message_sent"
        assert events[1]["event_type"] == "agent_reply"
        # Should be ordered by timestamp ascending
        assert events[0]["timestamp"] < events[1]["timestamp"]

    def test_clear_events(self):
        """清除指定会话的事件。"""
        from app.core.crud import clear_event_items, create_conversation, get_event_items, save_event_item
        create_conversation("conv_evt_clear", "single", "清除事件", "\U0001f916")

        save_event_item("conv_evt_clear", "test", 1.0, '{}')
        clear_event_items("conv_evt_clear")

        events = get_event_items("conv_evt_clear")
        assert events == []


# ===================================================================
# Uploaded File tests
# ===================================================================

class TestUploadedFile:

    def test_save_and_get(self):
        """保存和查询上传文件。"""
        from app.core.crud import get_all_uploaded_files, get_uploaded_file, save_uploaded_file

        save_uploaded_file(
            file_id="file_001",
            original_name="test.pdf",
            stored_name="stored_001.pdf",
            file_path="/uploads/stored_001.pdf",
            content_type="application/pdf",
            size=1024,
            extracted_text="Hello from PDF",
        )

        file = get_uploaded_file("file_001")
        assert file is not None
        assert file["original_name"] == "test.pdf"
        assert file["size"] == 1024
        assert file["extracted_text"] == "Hello from PDF"

        all_files = get_all_uploaded_files()
        assert any(f["id"] == "file_001" for f in all_files)

    def test_get_nonexistent_file_returns_none(self):
        """查询不存在的文件返回 None。"""
        from app.core.crud import get_uploaded_file

        result = get_uploaded_file("nonexistent_id")
        assert result is None
