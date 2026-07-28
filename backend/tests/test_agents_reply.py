"""Tests for agent reply logic — keyword routing, assign tags, no-question fallback."""
import pytest


def test_history_skips_large_code_dump_but_keeps_earlier_requirement():
    from app.agents.base import BaseAgent

    agent = BaseAgent()
    messages = agent._build_messages(
        "把按钮改成绿色",
        history=[
            {"sender": "user", "content": {"text": "做一个带导出功能的记账工具"}},
            {"sender": "agent_frontend", "content": {"text": "x" * 13_000}},
            {"sender": "user", "content": {"text": "把按钮改成绿色"}},
        ],
    )

    assert [item["content"] for item in messages] == [
        "做一个带导出功能的记账工具",
        "把按钮改成绿色",
    ]


class TestPMAgentReply:
    def test_assigns_frontend_on_ui_keywords(self):
        """PM should assign frontend agent for UI-related requests."""
        from app.agents.pm import PMAgent
        pm = PMAgent()
        reply = pm._generate_reply("做一个登录页面")
        assert "agent_frontend" in reply or "frontend" in reply.lower()

    def test_assigns_backend_on_api_keywords(self):
        """PM should assign backend agent for API-related requests."""
        from app.agents.pm import PMAgent
        pm = PMAgent()
        reply = pm._generate_reply("帮我写一个REST API接口")
        assert "agent_backend" in reply or "backend" in reply.lower()

    def test_vague_triggers_ask_user(self):
        """Very vague input should trigger [ask_user:] clarification."""
        from app.agents.pm import PMAgent
        pm = PMAgent()
        reply = pm._generate_reply("帮我做个")
        assert "[ask_user:" in reply

    def test_specific_input_does_not_ask(self):
        """Specific input should NOT trigger [ask_user:]."""
        from app.agents.pm import PMAgent
        pm = PMAgent()
        reply = pm._generate_reply("做一个天气预报应用")
        assert "[ask_user:" not in reply

    def test_assign_tag_format(self):
        """Assign tags should follow [assign:agent_xxx] format."""
        from app.agents.pm import PMAgent
        pm = PMAgent()
        reply = pm._generate_reply("做一个完整的网站")
        if "[assign:" in reply:
            import re
            matches = re.findall(r'\[assign:(\w+)\]', reply)
            for m in matches:
                assert m.startswith("agent_")


class TestBackendAgentReply:
    def test_no_question_in_api_reply(self):
        """Backend agent API reply should NOT contain question marks."""
        from app.agents.backend_agent import BackendAgent
        agent = BackendAgent()
        reply = agent._generate_reply("写个API接口")
        assert "？" not in reply
        assert "?" not in reply

    def test_api_reply_contains_code(self):
        """Backend agent API reply should contain code block."""
        from app.agents.backend_agent import BackendAgent
        agent = BackendAgent()
        reply = agent._generate_reply("写个API接口")
        assert "```" in reply


class TestFrontendAgentReply:
    def test_generates_html_on_ui_keywords(self):
        """Frontend agent should generate HTML for UI requests."""
        from app.agents.frontend import FrontendAgent
        agent = FrontendAgent()
        reply = agent._generate_reply("做一个登录页面")
        assert "<" in reply or "html" in reply.lower()
