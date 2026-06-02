"""Unit tests for agent_orchestrator.parse_create_agent_tag — [create_agent:{json}] tag parsing.

Pure logic tests: no LLM, no database, no network.
"""

import os
import sys

# Ensure the backend app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.agent_orchestrator import parse_create_agent_tag


class TestParseCreateAgentTagNormal:
    """Normal JSON payloads."""

    def test_simple_valid_json(self):
        buf = 'hello [create_agent:{"name": "test", "role": "coder"}] world'
        config, remaining = parse_create_agent_tag(buf)
        assert config == {"name": "test", "role": "coder"}
        assert remaining == "hello  world"

    def test_empty_json_object(self):
        buf = '[create_agent:{}]'
        config, remaining = parse_create_agent_tag(buf)
        assert config == {}
        assert remaining == ""

    def test_multiple_tags_returns_first(self):
        buf = '[create_agent:{"a":1}][create_agent:{"b":2}]'
        config, remaining = parse_create_agent_tag(buf)
        assert config == {"a": 1}
        assert remaining == '[create_agent:{"b":2}]'

    def test_tag_at_start(self):
        buf = '[create_agent:{"id":"x"}]trailing'
        config, remaining = parse_create_agent_tag(buf)
        assert config == {"id": "x"}
        assert remaining == "trailing"

    def test_tag_at_end(self):
        buf = 'leading[create_agent:{"id":"y"}]'
        config, remaining = parse_create_agent_tag(buf)
        assert config == {"id": "y"}
        assert remaining == "leading"


class TestParseCreateAgentTagEscapes:
    """JSON with special characters inside strings."""

    def test_json_with_closing_brace_in_string(self):
        buf = '[create_agent:{"name":"test}name","role":"dev"}]'
        config, _remaining = parse_create_agent_tag(buf)
        assert config is not None
        assert config["name"] == "test}name"

    def test_json_with_escaped_quote_in_string(self):
        buf = r'[create_agent:{"name":"say \"hello\"","role":"dev"}]'
        config, _remaining = parse_create_agent_tag(buf)
        assert config is not None
        assert config["name"] == 'say "hello"'

    def test_json_with_nested_objects(self):
        inner = '{"tools": {"read": true, "write": false}}'
        buf = f'[create_agent:{{"name":"a","config":{inner}}}]'
        config, _remaining = parse_create_agent_tag(buf)
        assert config is not None
        assert config["config"]["tools"]["read"] is True

    def test_json_with_nested_arrays(self):
        buf = '[create_agent:{"tags":["a","b","c"]}]'
        config, _remaining = parse_create_agent_tag(buf)
        assert config is not None
        assert config["tags"] == ["a", "b", "c"]

    def test_json_with_multiple_closing_braces_in_string(self):
        buf = '[create_agent:{"name":"a}b}c","x":1}]'
        config, _remaining = parse_create_agent_tag(buf)
        assert config is not None
        assert config["name"] == "a}b}c"
        assert config["x"] == 1


class TestParseCreateAgentTagIncomplete:
    """Incomplete or missing tags — should return (None, original buffer)."""

    def test_incomplete_tag_no_closing_bracket(self):
        buf = 'hello [create_agent:{"name":"test","role":"dev"}'
        config, remaining = parse_create_agent_tag(buf)
        assert config is None
        assert remaining == buf

    def test_no_tag_at_all(self):
        buf = 'just some plain text without any tags'
        config, remaining = parse_create_agent_tag(buf)
        assert config is None
        assert remaining == buf

    def test_empty_string(self):
        buf = ''
        config, remaining = parse_create_agent_tag(buf)
        assert config is None
        assert remaining == ""

    def test_tag_with_invalid_json(self):
        buf = '[create_agent:not-json-at-all]'
        config, _remaining = parse_create_agent_tag(buf)
        assert config is None

    def test_partial_json_truncated(self):
        buf = '[create_agent:{"name":"test"'
        config, remaining = parse_create_agent_tag(buf)
        assert config is None
        assert remaining == buf


class TestParseCreateAgentTagEdgeCases:
    """Edge cases and boundary conditions."""

    def test_whitespace_around_json(self):
        buf = '[create_agent:  {"name":"x"}  ]'
        config, _remaining = parse_create_agent_tag(buf)
        assert config is not None
        assert config["name"] == "x"

    def test_deeply_nested_json(self):
        buf = '[create_agent:{"a":{"b":{"c":{"d":"deep"}}}}]'
        config, _remaining = parse_create_agent_tag(buf)
        assert config is not None
        assert config["a"]["b"]["c"]["d"] == "deep"

    def test_json_with_unicode(self):
        buf = '[create_agent:{"name":"中文名称","role":"dev"}]'
        config, _remaining = parse_create_agent_tag(buf)
        assert config is not None
        assert config["name"] == "中文名称"

    def test_remaining_buffer_preserves_surrounding_text(self):
        buf = 'before [create_agent:{"x":1}] after'
        config, remaining = parse_create_agent_tag(buf)
        assert config == {"x": 1}
        assert remaining == "before  after"

    def test_escaped_backslash_before_quote(self):
        # JSON: {"path": "C:\\Users"}
        buf = '[create_agent:{"path":"C:\\\\Users"}]'
        config, _remaining = parse_create_agent_tag(buf)
        assert config is not None
        assert config["path"] == "C:\\Users"
