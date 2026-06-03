"""Tests for output validation functions in agent_orchestrator."""
import pytest
from app.services.agent_orchestrator import (
    detect_questions,
    check_format_compliance,
    check_tag_format,
    validate_agent_output,
)


class TestDetectQuestions:
    """Test question pattern detection."""

    def test_clean_text_returns_none(self):
        assert detect_questions("这是一个正常的回复，包含代码。") is None

    def test_question_mark_at_end(self):
        assert detect_questions("你想用什么数据库？") is not None

    def test_question_in_ask_user_tag_ignored(self):
        text = "[ask_user:你想用什么?|选项A::说明|选项B::说明]"
        assert detect_questions(text) is None

    def test_question_in_code_block_ignored(self):
        text = "```python\nif x == 0?:\n    pass\n```\n正常回复"
        assert detect_questions(text) is None

    def test_question_in_quotes_ignored(self):
        text = '回复包含 "Hello?" 这样的引号文本'
        assert detect_questions(text) is None

    def test_direct_question_detected(self):
        assert detect_questions("你想用 PostgreSQL 还是 MySQL？") is not None

    def test_polite_question_detected(self):
        assert detect_questions("请问需要哪些功能？") is not None

    def test_confirmation_request_detected(self):
        assert detect_questions("需要确认一下技术方案？") is not None

    def test_normal_text_with_question_in_middle_ignored(self):
        assert detect_questions("已经完成。还有什么问题吗？") is not None


class TestCheckFormatCompliance:
    """Test format compliance checking."""

    def test_frontend_with_html_passes(self):
        text = "摘要\n\n```html\n<!DOCTYPE html>\n<html>\n<head><style>body { margin: 0; padding: 20px; font-family: sans-serif; }</style></head>\n<body><h1>Hello World</h1><p>Welcome</p><script>console.log('ready')</script></body>\n</html>\n```"
        ok, _ = check_format_compliance(text, "agent_frontend")
        assert ok

    def test_frontend_without_code_fails(self):
        text = "这是一个前端回复但没有代码块，只是文字描述"
        ok, reason = check_format_compliance(text, "agent_frontend")
        assert not ok

    def test_backend_with_python_passes(self):
        text = "摘要\n\n```python\nfrom fastapi import FastAPI\napp = FastAPI()\n@app.get('/')\ndef root(): return {'status': 'ok'}\n```"
        ok, _ = check_format_compliance(text, "agent_backend")
        assert ok

    def test_backend_without_code_fails(self):
        text = "这是一个后端回复但没有代码块，只是文字描述"
        ok, reason = check_format_compliance(text, "agent_backend")
        assert not ok

    def test_pm_with_assign_passes(self):
        text = "方案概述\n1. 前端页面\n2. 后端接口\n[assign:agent_frontend] [assign:agent_backend]"
        ok, _ = check_format_compliance(text, "agent_pm")
        assert ok

    def test_pm_without_assign_fails(self):
        text = "方案概述\n1. 前端页面\n2. 后端接口"
        ok, reason = check_format_compliance(text, "agent_pm")
        assert not ok
        assert "missing" in reason

    def test_unknown_agent_passes(self):
        ok, _ = check_format_compliance("任何文本", "agent_unknown")
        assert ok

    def test_too_short_fails(self):
        ok, reason = check_format_compliance("短", "agent_frontend")
        assert not ok
        assert "too short" in reason


class TestCheckTagFormat:
    """Test tag format checking."""

    def test_pm_with_valid_tags_passes(self):
        text = "任务分配 [assign:agent_frontend] [assign:agent_backend]"
        ok, _ = check_tag_format(text, "agent_pm")
        assert ok

    def test_pm_without_tags_fails(self):
        text = "任务分配但没有标签"
        ok, reason = check_tag_format(text, "agent_pm")
        assert not ok
        assert "must output" in reason

    def test_pm_with_invalid_agent_id_fails(self):
        text = "任务分配 [assign:invalid_agent]"
        ok, reason = check_tag_format(text, "agent_pm")
        assert not ok
        assert "invalid" in reason

    def test_non_pm_agent_passes(self):
        ok, _ = check_tag_format("任何文本", "agent_frontend")
        assert ok


class TestValidateAgentOutput:
    """Test combined validation."""

    def test_valid_frontend_output_passes(self):
        text = (
            "[thinking]分析需求[/thinking]\n"
            "摘要\n\n"
            "```html\n<!DOCTYPE html>\n<html>\n<head><style>body { margin: 0; padding: 20px; }</style></head>\n"
            "<body><h1>Hello</h1><script>console.log('ready')</script></body>\n</html>\n```"
        )
        ok, _ = validate_agent_output(text, "agent_frontend")
        assert ok

    def test_valid_backend_output_passes(self):
        text = (
            "[thinking]分析需求[/thinking]\n"
            "摘要\n\n"
            "```python\nfrom fastapi import FastAPI\napp = FastAPI()\n```"
        )
        ok, _ = validate_agent_output(text, "agent_backend")
        assert ok

    def test_valid_pm_output_passes(self):
        text = "方案概述\n1. 前端\n2. 后端\n[assign:agent_frontend] [assign:agent_backend]"
        ok, _ = validate_agent_output(text, "agent_pm")
        assert ok

    def test_question_fails(self):
        text = "你想用什么数据库？"
        ok, reason = validate_agent_output(text, "agent_backend")
        assert not ok
        assert "anti-pattern" in reason

    def test_pm_no_assign_fails(self):
        text = "方案概述\n1. 前端\n2. 后端"
        ok, reason = validate_agent_output(text, "agent_pm")
        assert not ok
