"""Tests for debug engine - error parsing and fix prompt generation."""
import pytest
from app.core.debug_engine import parse_error, build_fix_prompt, extract_code_block


class TestParseError:
    def test_parse_name_error(self):
        output = 'Traceback (most recent call last):\n  File "test.py", line 5\n    print(x)\nNameError: name x is not defined'
        result = parse_error(output)
        assert result is not None
        assert result["error_type"] == "NameError"
        assert result["line_num"] == 5
        assert result["fixable"] is True

    def test_parse_syntax_error(self):
        output = '  File "test.py", line 3\n    def foo(\n           ^\nSyntaxError: unexpected EOF'
        result = parse_error(output)
        assert result is not None
        assert result["error_type"] == "SyntaxError"
        assert result["fixable"] is True

    def test_parse_type_error(self):
        output = 'Traceback (most recent call last):\n  File "test.py", line 10\n    foo(1, 2, 3)\nTypeError: foo() takes 2 arguments but 3 were given'
        result = parse_error(output)
        assert result is not None
        assert result["error_type"] == "TypeError"
        assert result["fixable"] is True

    def test_parse_module_not_found(self):
        output = 'Traceback (most recent call last):\n  File "test.py", line 1\n    import nonexistent\nModuleNotFoundError: No module named nonexistent'
        result = parse_error(output)
        assert result is not None
        assert result["error_type"] == "ModuleNotFoundError"
        assert result["fixable"] is True

    def test_parse_assertion_error_not_fixable(self):
        output = 'Traceback (most recent call last):\n  File "test.py", line 5\n    assert False\nAssertionError'
        result = parse_error(output)
        assert result is not None
        assert result["error_type"] == "AssertionError"
        assert result["fixable"] is False

    def test_parse_recursion_error_not_fixable(self):
        output = 'Traceback (most recent call last):\nRecursionError: maximum recursion depth exceeded'
        result = parse_error(output)
        assert result is not None
        assert result["error_type"] == "RecursionError"
        assert result["fixable"] is False

    def test_parse_empty_output(self):
        assert parse_error("") is None
        assert parse_error(None) is None

    def test_parse_no_traceback(self):
        output = "Error: something went wrong"
        result = parse_error(output)
        assert result is not None
        assert result["error_type"] in ("Error", "Unknown")

    def test_parse_exit_code(self):
        output = "Process exited with code 1"
        result = parse_error(output)
        assert result is None or result["fixable"] is False

    def test_parse_key_error(self):
        output = 'Traceback (most recent call last):\n  File "test.py", line 3\n    d["key"]\nKeyError: key'
        result = parse_error(output)
        assert result is not None
        assert result["error_type"] == "KeyError"
        assert result["fixable"] is True

    def test_parse_index_error(self):
        output = 'Traceback (most recent call last):\n  File "test.py", line 3\n    lst[10]\nIndexError: list index out of range'
        result = parse_error(output)
        assert result is not None
        assert result["error_type"] == "IndexError"
        assert result["fixable"] is True

    def test_parse_file_not_found(self):
        output = 'Traceback (most recent call last):\n  File "test.py", line 3\n    open("missing.txt")\nFileNotFoundError: No such file'
        result = parse_error(output)
        assert result is not None
        assert result["error_type"] == "FileNotFoundError"
        assert result["fixable"] is True


class TestBuildFixPrompt:
    def test_prompt_contains_error_info(self):
        error_info = {
            "error_type": "NameError",
            "error_msg": "name x is not defined",
            "line_num": 5,
            "fix_hint": "add missing import or variable definition",
        }
        prompt = build_fix_prompt(error_info, "def foo(): pass", "task")
        assert "NameError" in prompt
        assert "5" in prompt
        assert "def foo" in prompt

    def test_prompt_contains_attempt_number(self):
        error_info = {"error_type": "NameError", "error_msg": "err", "line_num": 1, "fix_hint": "fix"}
        prompt = build_fix_prompt(error_info, "code", "task", attempt=2)
        assert "2" in prompt

    def test_prompt_emphasizes_minimal_changes(self):
        error_info = {"error_type": "NameError", "error_msg": "err", "line_num": 1, "fix_hint": "fix"}
        prompt = build_fix_prompt(error_info, "code", "task")
        assert "只修改" in prompt or "minimal" in prompt.lower()


class TestExtractCodeBlock:
    def test_extract_python_code(self):
        text = "Here is the fix:\n```python\ndef hello():\n    return 1\n```\nDone."
        result = extract_code_block(text)
        assert result is not None
        assert "def hello" in result

    def test_extract_generic_code(self):
        text = "```\ndef hello():\n    return 1\n```"
        result = extract_code_block(text)
        assert result is not None

    def test_no_code_block(self):
        text = "Just some text without code"
        result = extract_code_block(text)
        assert result is None

    def test_code_without_fence(self):
        text = "def hello():\n    return 1"
        result = extract_code_block(text)
        assert result is not None
        assert "def hello" in result


class TestDebugAgent:
    def test_agent_attributes(self):
        from app.agents.debug_agent import DebugAgent
        agent = DebugAgent()
        assert agent.agent_id == "agent_debugger"
        assert agent.name == "Debug 助手"
        assert agent.avatar == "🔧"

    def test_agent_debug_reply(self):
        from app.agents.debug_agent import DebugAgent
        agent = DebugAgent()
        reply = agent._generate_reply("代码报错了 TypeError")
        assert "修复" in reply or "错误" in reply or "thinking" in reply
