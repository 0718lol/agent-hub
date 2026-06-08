"""Tests for GitHub Issue auto-resolution engine."""
import pytest
from unittest.mock import AsyncMock
from app.core.issue_resolver import parse_issue, _keyword_localize, resolve_issue


class TestParseIssue:
    def test_parse_basic_issue(self):
        issue = {"title": "Login broken", "body": "Cannot login", "labels": [{"name": "bug"}], "number": 42, "html_url": "https://github.com/test/issue/42"}
        result = parse_issue(issue)
        assert result["title"] == "Login broken"
        assert result["body"] == "Cannot login"
        assert result["labels"] == ["bug"]
        assert result["number"] == 42

    def test_parse_empty_issue(self):
        result = parse_issue({})
        assert result["title"] == ""
        assert result["body"] == ""
        assert result["labels"] == []

    def test_parse_string_labels(self):
        issue = {"labels": ["bug", "urgent"]}
        result = parse_issue(issue)
        assert result["labels"] == ["bug", "urgent"]


class TestKeywordLocalize:
    def test_finds_relevant_file(self):
        results = _keyword_localize("websocket connection error")
        assert len(results) > 0
        # Should find websocket.py
        files = [r["file"] for r in results]
        assert any("websocket" in f.lower() for f in files)

    def test_returns_empty_for_no_match(self):
        results = _keyword_localize("xyznonexistent")
        assert len(results) == 0


class TestResolveIssue:
    @pytest.mark.asyncio
    async def test_no_llm_returns_keyword_results(self):
        issue = {"title": "websocket error", "body": "connection failed"}
        result = await resolve_issue(issue, llm_client=None)
        assert result["status"] == "no_files_found" or result["status"] == "no_fixes"

    @pytest.mark.asyncio
    async def test_with_mock_llm(self):
        mock_client = AsyncMock()
        async def mock_stream(messages):
            yield "backend/app/core/websocket.py"
        mock_client.chat_stream = mock_stream

        issue = {"title": "websocket error", "body": "connection failed"}
        result = await resolve_issue(issue, llm_client=mock_client)
        assert result["status"] in ("resolved", "no_fixes", "all_invalid", "no_files_found")
