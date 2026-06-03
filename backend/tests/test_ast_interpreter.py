"""Tests for AST interpreter sandbox."""
import pytest
import asyncio
from app.core.ast_interpreter import SafeASTInterpreter


@pytest.fixture
def interpreter():
    return SafeASTInterpreter()


class TestAstInterpreterBasic:
    """Basic execution tests."""

    @pytest.mark.asyncio
    async def test_simple_assignment(self, interpreter):
        result = await interpreter.execute("x = 5")
        assert result["success"] is True
        assert result["result"] == 5

    @pytest.mark.asyncio
    async def test_arithmetic(self, interpreter):
        result = await interpreter.execute("x = 2 + 3")
        assert result["success"] is True
        assert result["result"] == 5

    @pytest.mark.asyncio
    async def test_string_assignment(self, interpreter):
        result = await interpreter.execute("s = 'hello'")
        assert result["success"] is True
        assert result["result"] == "hello"

    @pytest.mark.asyncio
    async def test_list_assignment(self, interpreter):
        result = await interpreter.execute("nums = [1, 2, 3]")
        assert result["success"] is True
        assert result["result"] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_dict_assignment(self, interpreter):
        result = await interpreter.execute("d = {'a': 1, 'b': 2}")
        assert result["success"] is True
        assert result["result"] == {"a": 1, "b": 2}

    @pytest.mark.asyncio
    async def test_boolean_operations(self, interpreter):
        result = await interpreter.execute("x = True and False")
        assert result["success"] is True
        assert result["result"] is False

    @pytest.mark.asyncio
    async def test_comparison(self, interpreter):
        result = await interpreter.execute("x = 5 > 3")
        assert result["success"] is True
        assert result["result"] is True


class TestAstInterpreterSecurity:
    """Security tests - sandbox escape prevention."""

    @pytest.mark.asyncio
    async def test_import_blocked(self, interpreter):
        result = await interpreter.execute("import os")
        assert result["success"] is False or result.get("error") is not None

    @pytest.mark.asyncio
    async def test_exec_blocked(self, interpreter):
        result = await interpreter.execute("exec('import os')")
        assert result["success"] is False or result.get("error") is not None

    @pytest.mark.asyncio
    async def test_eval_blocked(self, interpreter):
        result = await interpreter.execute("eval('__import__(\"os\")')")
        assert result["success"] is False or result.get("error") is not None

    @pytest.mark.asyncio
    async def test_dunder_class_blocked(self, interpreter):
        result = await interpreter.execute("x = ().__class__.__bases__[0]")
        assert result["success"] is False or result.get("error") is not None

    @pytest.mark.asyncio
    async def test_dunder_builtins_blocked(self, interpreter):
        result = await interpreter.execute("x = __builtins__")
        assert result["success"] is False or result.get("error") is not None

    @pytest.mark.asyncio
    async def test_attribute_access_blocked(self, interpreter):
        result = await interpreter.execute("x = getattr(__builtins__, '__import__')")
        assert result["success"] is False or result.get("error") is not None


class TestAstInterpreterEdgeCases:
    """Edge case tests."""

    @pytest.mark.asyncio
    async def test_empty_code(self, interpreter):
        result = await interpreter.execute("")
        assert result is not None

    @pytest.mark.asyncio
    async def test_multiline_code(self, interpreter):
        result = await interpreter.execute("x = 1\ny = 2\nz = x + y\nz")
        assert result["success"] is True
        assert result["result"] == 3

    @pytest.mark.asyncio
    async def test_conditional(self, interpreter):
        result = await interpreter.execute("x = 10\nif x > 5:\n    y = 'big'\nelse:\n    y = 'small'\ny")
        assert result["success"] is True
        assert result["result"] == "big"

    @pytest.mark.asyncio
    async def test_nested_dicts(self, interpreter):
        result = await interpreter.execute("data = {'a': {'b': 42}}\ndata['a']['b']")
        assert result["success"] is True
        assert result["result"] == 42

    @pytest.mark.asyncio
    async def test_negative_numbers(self, interpreter):
        result = await interpreter.execute("x = -5 + 3")
        assert result["success"] is True
        assert result["result"] == -2

    @pytest.mark.asyncio
    async def test_string_concatenation(self, interpreter):
        result = await interpreter.execute("a = 'hello'\nb = ' world'\na + b")
        assert result["success"] is True
        assert result["result"] == "hello world"
