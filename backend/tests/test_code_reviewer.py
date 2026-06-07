"""Tests for Code Review Agent."""
import pytest
from unittest.mock import AsyncMock

from app.core.code_review_rules import rule_based_review
from app.services.code_review_service import review_code, calculate_score, parse_llm_review, self_healing_review


class TestRuleBasedReview:
    def test_hardcoded_password_detected(self):
        code = 'password = "my_secret_password_123"'
        issues = rule_based_review(code)
        assert any(i["rule"] == "hardcoded_secret" for i in issues)

    def test_sql_injection_detected(self):
        code = 'query = f"SELECT * FROM users WHERE id = {user_id}"'
        issues = rule_based_review(code)
        assert any(i["rule"] == "sql_injection" for i in issues)

    def test_bare_except_detected(self):
        code = "try:\n    pass\nexcept:\n    pass"
        issues = rule_based_review(code)
        assert any(i["rule"] == "bare_except" for i in issues)

    def test_clean_code_no_issues(self):
        code = "def hello():\n    return 'world'"
        issues = rule_based_review(code)
        assert len(issues) == 0


class TestCalculateScore:
    def test_no_issues(self):
        assert calculate_score([])["overall"] == 10.0

    def test_high_issue(self):
        assert calculate_score([{"severity": "high"}])["overall"] == 8.0

    def test_multiple_issues(self):
        issues = [{"severity": "high"}, {"severity": "medium"}, {"severity": "low"}]
        assert calculate_score(issues)["overall"] == 6.5


class TestParseLlmReview:
    def test_valid_json(self):
        text = '{"issues": [{"severity": "high"}]}'
        assert len(parse_llm_review(text)) == 1

    def test_invalid_json(self):
        assert len(parse_llm_review("not json")) == 0


class TestReviewCode:
    @pytest.mark.asyncio
    async def test_rule_based(self):
        code = 'password = "test123456789"'
        result = await review_code(code, agent=None)
        assert len(result["issues"]) > 0

    @pytest.mark.asyncio
    async def test_clean_code(self):
        code = "def hello():\n    return 1"
        result = await review_code(code, agent=None)
        assert result["score"]["overall"] == 10.0


class TestSelfHealing:
    @pytest.mark.asyncio
    async def test_clean_passes(self):
        agent = AsyncMock()
        async def stream(p):
            yield '{"issues": []}'
        agent.stream_reply = stream
        r = await self_healing_review("x = 1", agent)
        assert r["status"] == "passed"


class TestCodeReviewerAgent:
    def test_agent_exists(self):
        from app.agents.code_reviewer import CodeReviewerAgent
        a = CodeReviewerAgent()
        assert a.agent_id == "agent_reviewer"
