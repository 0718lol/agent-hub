"""Tests for agent reply logic — keyword routing, assign tags, no-question fallback."""
import pytest


def test_disabled_thinking_removes_visible_reasoning_instructions():
    from app.agents.base import _without_explicit_thinking

    prompt = (
        "你是前端工程师。\n"
        "【思维过程】：\n"
        "- 先用 [thinking]分析需求[/thinking]。\n"
        "- 思考完毕后再输出最终答案。\n"
        "请输出完整 HTML。"
    )

    result = _without_explicit_thinking(prompt)

    assert "[thinking]" not in result
    assert "思维过程" not in result
    assert "只输出最终结果" in result
    assert "请输出完整 HTML" in result


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
