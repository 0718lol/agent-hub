"""Safe AST Interpreter — A secure asynchronous Abstract Syntax Tree Python evaluator.

This module parses LLM-generated Python code into an Abstract Syntax Tree (AST)
and executes it step-by-step in an asynchronous restricted sandbox, whitelisting builtins,
blocking dangerous private attributes (e.g. __class__), preventing module imports,
and limiting loop iterations to avoid denial-of-service resource exhaustion.
"""

import ast
import asyncio
import io
import operator
from collections.abc import Callable
from typing import Any


def _make_safe_builtin(fn):
    """Wrap a builtin function so its __builtins__ dict is empty, preventing sandbox escape."""
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)
    wrapper.__name__ = getattr(fn, "__name__", "builtin")
    try:
        wrapper.__builtins__ = {}
    except AttributeError:
        pass
    return wrapper

class BreakException(Exception):
    """Exception raised to break out of a loop in AST interpreter."""
    pass

class ContinueException(Exception):
    """Exception raised to continue a loop in AST interpreter."""
    pass

_MAX_EXPONENT = 1000
_MAX_BIT_LENGTH = 100_000
_MAX_SHIFT_BITS = 1000
_MAX_SEQ_LENGTH = 100_000
_MAX_STDOUT_CHARS = 100_000
_BLOCKED_ATTR_NAMES = frozenset({"format", "format_map", "mro"})


class SafeASTInterpreter:
    """A highly secure, zero-dependency asynchronous AST interpreter for Python."""

    def __init__(self, allowed_tools: dict[str, Callable] = None, max_iterations: int = 1000):
        self.allowed_tools = allowed_tools or {}
        self.variables = {}
        self.iteration_count = 0
        self.step_count = 0
        self.max_iterations = max_iterations
        self.max_steps = max(max_iterations * 50, 50_000)
        self.stdout_buffer = io.StringIO()
        self._output_buffer = None
        self._safe_print_fn = None

        # Secure binary operations map
        self.binops = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
            ast.LShift: operator.lshift,
            ast.RShift: operator.rshift,
            ast.BitOr: operator.or_,
            ast.BitXor: operator.xor,
            ast.BitAnd: operator.and_
        }

    def _safe_print(self, *args, sep=' ', end='\n', file=None, flush=False):
        """Thread-safe print replacement that writes to internal buffer instead of sys.stdout."""
        if self._output_buffer is not None:
            text = sep.join(str(a) for a in args) + end
            self._output_buffer.write(text)

    async def execute(self, code_str: str) -> dict:
        """Executes code_str asynchronously and returns execution summary dictionary."""
        self.iteration_count = 0
        self.step_count = 0
        buf = io.StringIO()
        self._output_buffer = buf

        def _isolated_print(*args, sep=" ", end="\n", file=None, flush=False):
            del file, flush
            text = sep.join(str(a) for a in args) + end
            if buf.tell() + len(text) > _MAX_STDOUT_CHARS:
                raise MemoryError("🔒 输出安全限制: 标准输出内容超出上限")
            buf.write(text)

        self._safe_print_fn = _make_safe_builtin(_isolated_print)
        try:
            tree = ast.parse(code_str)
            result = None
            for node in tree.body:
                result = await self.visit(node)
            return {
                "success": True,
                "stdout": buf.getvalue(),
                "result": result,
                "error": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": buf.getvalue(),
                "result": None,
                "error": f"{type(e).__name__}: {e!s}"
            }
        finally:
            self._output_buffer = None
            self._safe_print_fn = None

    async def visit(self, node: ast.AST) -> Any:
        if node is None:
            return None
        self.step_count += 1
        if self.step_count > self.max_steps:
            raise RuntimeError(f"🔒 执行安全限制: AST 求值步数超过上限 {self.max_steps}")
        method_name = f"visit_{type(node).__name__}"
        visitor = getattr(self, method_name, None)
        if visitor is None:
            raise NotImplementedError(f"🔒 安全沙箱不支持的 Python 语法类型: '{type(node).__name__}'")
        return await visitor(node)

    async def visit_Module(self, node: ast.Module) -> Any:
        res = None
        for stmt in node.body:
            res = await self.visit(stmt)
        return res

    async def visit_Expr(self, node: ast.Expr) -> Any:
        return await self.visit(node.value)

    async def visit_Constant(self, node: ast.Constant) -> Any:
        return node.value

    async def visit_Name(self, node: ast.Name) -> Any:
        if node.id in self.variables:
            return self.variables[node.id]
        if node.id in self.allowed_tools:
            return self.allowed_tools[node.id]

        # Inject standard whitelisted built-in functions/constants
        safe_builtins = {
            "print": self._safe_print_fn or self._safe_print,
            "len": _make_safe_builtin(len),
            "range": range,
            "abs": _make_safe_builtin(abs),
            "round": _make_safe_builtin(round),
            "bool": bool,
            "str": str,
            "int": int,
            "float": float,
            "list": list,
            "tuple": tuple,
            "dict": dict,
            "set": set,
            "sorted": _make_safe_builtin(sorted),
            "reversed": reversed,
            "any": _make_safe_builtin(any),
            "all": _make_safe_builtin(all),
            "min": _make_safe_builtin(min),
            "max": _make_safe_builtin(max),
            "sum": _make_safe_builtin(sum),
            "enumerate": enumerate,
            "zip": zip,
            "True": True,
            "False": False,
            "None": None
        }
        if node.id in safe_builtins:
            return safe_builtins[node.id]
        raise NameError(f"未定义或未授权的变量/函数: '{node.id}'")

    async def visit_Assign(self, node: ast.Assign) -> Any:
        value = await self.visit(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.variables[target.id] = value
            elif isinstance(target, ast.Subscript):
                obj = await self.visit(target.value)
                slice_val = await self.visit(target.slice)
                obj[slice_val] = value
            else:
                raise NotImplementedError("🔒 不支持的赋值目标语法")
        return value

    async def visit_BinOp(self, node: ast.BinOp) -> Any:
        left = await self.visit(node.left)
        right = await self.visit(node.right)
        op_type = type(node.op)
        if op_type is ast.Pow:
            if isinstance(right, (int, float)) and abs(right) > _MAX_EXPONENT:
                raise ValueError(f"🔒 算术安全限制: 指数 {right} 超出安全上限 {_MAX_EXPONENT}")
            if isinstance(left, int) and isinstance(right, int) and right > 0:
                if max(left.bit_length(), 1) * right > _MAX_BIT_LENGTH:
                    raise ValueError("🔒 算术安全限制: 幂运算结果位数超出安全上限")
        elif op_type is ast.LShift:
            if isinstance(right, int) and (right < 0 or right > _MAX_SHIFT_BITS):
                raise ValueError(f"🔒 算术安全限制: 左移位数超出安全范围 [0, {_MAX_SHIFT_BITS}]")
            if isinstance(left, int) and isinstance(right, int) and max(left.bit_length(), 1) + right > _MAX_BIT_LENGTH:
                raise ValueError("🔒 算术安全限制: 位移结果超出安全上限")
        elif op_type is ast.Mult:
            if isinstance(left, (str, bytes, list, tuple)) and isinstance(right, int):
                if right > 0 and len(left) * right > _MAX_SEQ_LENGTH:
                    raise MemoryError(f"🔒 内存安全限制: 序列重复长度超过上限 {_MAX_SEQ_LENGTH}")
            elif isinstance(right, (str, bytes, list, tuple)) and isinstance(left, int):
                if left > 0 and len(right) * left > _MAX_SEQ_LENGTH:
                    raise MemoryError(f"🔒 内存安全限制: 序列重复长度超过上限 {_MAX_SEQ_LENGTH}")
        elif op_type is ast.Add:
            if isinstance(left, (str, bytes, list, tuple)) and isinstance(right, (str, bytes, list, tuple)):
                if len(left) + len(right) > _MAX_SEQ_LENGTH * 2:
                    raise MemoryError("🔒 内存安全限制: 序列拼接长度超过安全上限")
        if op_type in self.binops:
            return self.binops[op_type](left, right)
        raise NotImplementedError(f"不支持的二进制算子: {op_type.__name__}")

    async def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = await self.visit(node.operand)
        ops = {
            ast.UAdd: operator.pos,
            ast.USub: operator.neg,
            ast.Not: operator.not_,
            ast.Invert: operator.invert
        }
        op_type = type(node.op)
        if op_type in ops:
            return ops[op_type](operand)
        raise NotImplementedError(f"不支持的单目算子: {op_type.__name__}")

    async def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        if isinstance(node.op, ast.And):
            val = None
            for val_node in node.values:
                val = await self.visit(val_node)
                if not val:
                    return val
            return val
        elif isinstance(node.op, ast.Or):
            val = None
            for val_node in node.values:
                val = await self.visit(val_node)
                if val:
                    return val
            return val
        raise NotImplementedError("不支持的布尔算子")

    async def visit_Compare(self, node: ast.Compare) -> Any:
        left = await self.visit(node.left)
        ops = {
            ast.Eq: operator.eq,
            ast.NotEq: operator.ne,
            ast.Lt: operator.lt,
            ast.LtE: operator.le,
            ast.Gt: operator.gt,
            ast.GtE: operator.ge,
            ast.Is: lambda a, b: a is b,
            ast.IsNot: lambda a, b: a is not b,
            ast.In: lambda a, b: a in b,
            ast.NotIn: lambda a, b: a not in b
        }
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            right = await self.visit(comparator)
            op_type = type(op)
            if op_type not in ops:
                raise NotImplementedError(f"不支持的比较算子: {op_type.__name__}")
            if not ops[op_type](left, right):
                return False
            left = right
        return True

    async def visit_If(self, node: ast.If) -> Any:
        cond = await self.visit(node.test)
        res = None
        if cond:
            for stmt in node.body:
                res = await self.visit(stmt)
        else:
            for stmt in node.orelse:
                res = await self.visit(stmt)
        return res

    async def visit_Pass(self, node: ast.Pass) -> Any:
        return None

    async def visit_Break(self, node: ast.Break) -> Any:
        raise BreakException()

    async def visit_Continue(self, node: ast.Continue) -> Any:
        raise ContinueException()

    async def visit_While(self, node: ast.While) -> Any:
        res = None
        while await self.visit(node.test):
            self.iteration_count += 1
            if self.iteration_count > self.max_iterations:
                raise RuntimeError(f"🔒 循环安全限制: 已超过最大迭代上限 {self.max_iterations} 步，执行被安全熔断！")
            try:
                for stmt in node.body:
                    res = await self.visit(stmt)
            except BreakException:
                break
            except ContinueException:
                continue
        return res

    async def visit_For(self, node: ast.For) -> Any:
        res = None
        items = await self.visit(node.iter)
        for item in items:
            self.iteration_count += 1
            if self.iteration_count > self.max_iterations:
                raise RuntimeError(f"🔒 循环安全限制: 已超过最大迭代上限 {self.max_iterations} 步，执行被安全熔断！")
            if isinstance(node.target, ast.Name):
                self.variables[node.target.id] = item
            else:
                raise NotImplementedError("不支持的 For 循环非解包目标")
            try:
                for stmt in node.body:
                    res = await self.visit(stmt)
            except BreakException:
                break
            except ContinueException:
                continue
        return res

    async def visit_Call(self, node: ast.Call) -> Any:
        func = await self.visit(node.func)
        args = [await self.visit(arg) for arg in node.args]
        kwargs = {kw.arg: await self.visit(kw.value) for kw in node.keywords}

        # Block calling dangerous private built-in attributes
        func_name = getattr(func, "__name__", "")
        if func_name and (func_name.startswith("_") or func_name in _BLOCKED_ATTR_NAMES):
            raise PermissionError(f"🔒 安全拦截: 严禁调用受限方法 '{func_name}'！")

        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            res = func(*args, **kwargs)
            if asyncio.iscoroutine(res):
                return await res
            return res

    async def visit_Attribute(self, node: ast.Attribute) -> Any:
        obj = await self.visit(node.value)
        attr = node.attr
        if attr.startswith("_") or attr in _BLOCKED_ATTR_NAMES:
            raise PermissionError(f"🔒 安全拦截: 禁止访问受限属性或格式化逃逸方法 '{attr}'！")
        return getattr(obj, attr)

    async def visit_Subscript(self, node: ast.Subscript) -> Any:
        obj = await self.visit(node.value)
        slice_val = await self.visit(node.slice)
        return obj[slice_val]

    async def visit_Index(self, node: ast.Index) -> Any:
        # Compatibility with Python 3.8 and below
        return await self.visit(node.value)

    async def visit_Slice(self, node: ast.Slice) -> Any:
        lower = await self.visit(node.lower) if node.lower else None
        upper = await self.visit(node.upper) if node.upper else None
        step = await self.visit(node.step) if node.step else None
        return slice(lower, upper, step)

    async def visit_List(self, node: ast.List) -> Any:
        res = []
        for elt in node.elts:
            res.append(await self.visit(elt))
        return res

    async def visit_Tuple(self, node: ast.Tuple) -> Any:
        res = []
        for elt in node.elts:
            res.append(await self.visit(elt))
        return tuple(res)

    async def visit_Dict(self, node: ast.Dict) -> Any:
        keys = []
        for k in node.keys:
            keys.append(await self.visit(k))
        values = []
        for v in node.values:
            values.append(await self.visit(v))
        return dict(zip(keys, values, strict=False))

    async def visit_Set(self, node: ast.Set) -> Any:
        res = set()
        for elt in node.elts:
            res.add(await self.visit(elt))
        return res

    async def visit_Import(self, node: ast.Import) -> Any:
        raise PermissionError("🔒 安全拦截: 解释器中严禁在运行时执行 import 导入模块操作！")

    async def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        raise PermissionError("🔒 安全拦截: 解释器中严禁在运行时执行 import 导入模块操作！")
