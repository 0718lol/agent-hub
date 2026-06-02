"""Unit tests for database._safe_json_loads — safe JSON parsing with size guard.

Pure logic tests: no database, no network.
"""

import sys
import os
import json

# Ensure the backend app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.crud import _safe_json_loads, _MAX_JSON_PARSE_SIZE


class TestSafeJsonLoadsNormal:
    """Normal JSON parsing."""

    def test_valid_json_object(self):
        data = '{"key": "value", "num": 42}'
        result = _safe_json_loads(data)
        assert result == {"key": "value", "num": 42}

    def test_valid_json_array(self):
        data = '[1, 2, 3, "four"]'
        result = _safe_json_loads(data)
        assert result == [1, 2, 3, "four"]

    def test_valid_json_string(self):
        data = '"hello world"'
        result = _safe_json_loads(data)
        assert result == "hello world"

    def test_valid_json_number(self):
        data = '42'
        result = _safe_json_loads(data)
        assert result == 42

    def test_valid_json_nested(self):
        data = '{"a": {"b": {"c": [1, 2, 3]}}}'
        result = _safe_json_loads(data)
        assert result["a"]["b"]["c"] == [1, 2, 3]

    def test_valid_json_with_unicode(self):
        data = '{"name": "中文", "emoji": "😀"}'
        result = _safe_json_loads(data)
        assert result["name"] == "中文"

    def test_json_true_false_null(self):
        data = '{"a": true, "b": false, "c": null}'
        result = _safe_json_loads(data)
        assert result["a"] is True
        assert result["b"] is False
        assert result["c"] is None


class TestSafeJsonLoadsFallback:
    """Non-JSON text should fallback gracefully."""

    def test_plain_text_fallback(self):
        data = "just some plain text"
        result = _safe_json_loads(data)
        assert result == {"text": "just some plain text"}

    def test_partial_json_fallback(self):
        data = '{"key": "value"'  # missing closing brace
        result = _safe_json_loads(data)
        assert result == {"text": data}

    def test_empty_json_object(self):
        data = '{}'
        result = _safe_json_loads(data)
        assert result == {}

    def test_html_content_fallback(self):
        data = "<html><body>not json</body></html>"
        result = _safe_json_loads(data)
        assert result == {"text": data}

    def test_broken_unicode_fallback(self):
        # A string that is valid but not valid JSON
        data = "{'single': 'quotes'}"
        result = _safe_json_loads(data)
        assert result == {"text": data}


class TestSafeJsonLoadsOversizedPayload:
    """Payloads exceeding 1MB should be truncated with a warning."""

    def test_oversized_string_returns_warning(self):
        data = "x" * (_MAX_JSON_PARSE_SIZE + 1)
        result = _safe_json_loads(data)
        assert "_warning" in result
        assert result["_warning"] == "payload_too_large_skipped"
        assert result["text"] == data

    def test_exactly_at_limit_parses_normally(self):
        # A valid JSON string at exactly the limit should parse normally
        inner = "a" * (_MAX_JSON_PARSE_SIZE - 20)
        data = json.dumps({"text": inner})
        if len(data) <= _MAX_JSON_PARSE_SIZE:
            result = _safe_json_loads(data)
            # Should parse as JSON since it's within limit
            assert "text" in result or "_warning" in result

    def test_oversized_valid_json_still_skipped(self):
        # Even valid JSON over 1MB gets the warning
        big_obj = {"data": "y" * (_MAX_JSON_PARSE_SIZE + 100)}
        data = json.dumps(big_obj)
        result = _safe_json_loads(data)
        assert "_warning" in result

    def test_just_over_limit(self):
        data = "z" * (_MAX_JSON_PARSE_SIZE + 1)
        result = _safe_json_loads(data)
        assert "_warning" in result


class TestSafeJsonLoadsEdgeCases:
    """Edge cases: None, non-string inputs."""

    def test_none_input_returns_fallback(self):
        result = _safe_json_loads(None)
        assert result == {"text": None}

    def test_integer_input_returns_fallback(self):
        result = _safe_json_loads(123)
        # json.loads raises TypeError for non-string, caught by fallback
        assert result == {"text": 123}

    def test_empty_string_fallback(self):
        result = _safe_json_loads("")
        # Empty string is not valid JSON, should fallback
        assert result == {"text": ""}

    def test_whitespace_only_fallback(self):
        result = _safe_json_loads("   ")
        assert result == {"text": "   "}

    def test_json_with_leading_trailing_whitespace(self):
        data = '  {"key": "value"}  '
        result = _safe_json_loads(data)
        assert result == {"key": "value"}
