import sys
import os
import unittest
import asyncio
import shutil
from unittest.mock import AsyncMock, patch

# Setup import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.ast_interpreter import SafeASTInterpreter
from app.tools.code_agent_tools import SafePythonExecutorTool
from app.tools.registry import execute_tool_call

class TestASTInterpreter(unittest.IsolatedAsyncioTestCase):

    async def test_basic_arithmetic_and_variables(self):
        """Test safe variables, arithmetic operations and standard whitelisted builtins."""
        interpreter = SafeASTInterpreter()
        code = """
a = 15
b = 10
c = (a * b) - 50
print("Calculated c:", c)
c
"""
        res = await interpreter.execute(code)
        self.assertTrue(res["success"])
        self.assertEqual(res["stdout"].strip(), "Calculated c: 100")
        self.assertEqual(res["result"], 100)

    async def test_string_and_list_manipulation(self):
        """Test basic string manipulations, attribute lookups and lists."""
        interpreter = SafeASTInterpreter()
        code = """
greet = "Hello " + "World"
lst = [1, 2, 3]
lst.append(4)
print(greet, lst)
lst
"""
        res = await interpreter.execute(code)
        self.assertTrue(res["success"])
        self.assertEqual(res["stdout"].strip(), "Hello World [1, 2, 3, 4]")
        self.assertEqual(res["result"], [1, 2, 3, 4])

    async def test_conditionals_and_comparisons(self):
        """Test comparison operators (Eq, Lt, Gt, In) and conditional branch execution."""
        interpreter = SafeASTInterpreter()
        code = """
score = 85
grade = "F"
if score >= 90:
    grade = "A"
elif score >= 80:
    grade = "B"
else:
    grade = "C"

is_b_grade = grade == "B"
print("Grade is:", grade)
is_b_grade
"""
        res = await interpreter.execute(code)
        self.assertTrue(res["success"])
        self.assertEqual(res["stdout"].strip(), "Grade is: B")
        self.assertEqual(res["result"], True)

    async def test_loops_and_iteration_bounds(self):
        """Test loops (for, while) and iteration bounding protection."""
        interpreter = SafeASTInterpreter(max_iterations=100)
        
        # 1. Normal execution
        code_ok = """
total = 0
for i in range(10):
    total = total + i
total
"""
        res_ok = await interpreter.execute(code_ok)
        self.assertTrue(res_ok["success"])
        self.assertEqual(res_ok["result"], 45)

        # 2. Infinite While loop triggering bound
        code_infinite_while = """
x = 0
while x < 5:
    # infinite loop by not updating x
    pass
"""
        res_fail_while = await interpreter.execute(code_infinite_while)
        self.assertFalse(res_fail_while["success"])
        self.assertIn("RuntimeError", res_fail_while["error"])

        # 3. Endless For loop triggering bound
        code_large_for = """
total = 0
for i in range(500):
    total = total + i
"""
        res_fail_for = await interpreter.execute(code_large_for)
        self.assertFalse(res_fail_for["success"])
        self.assertIn("RuntimeError", res_fail_for["error"])

    async def test_security_imports_and_backdoors_blocking(self):
        """Test that forbidden statements (import, private attributes, dangerous builtins) are blocked."""
        interpreter = SafeASTInterpreter()

        # 1. Direct imports
        res_imp = await interpreter.execute("import os")
        self.assertFalse(res_imp["success"])
        self.assertIn("PermissionError", res_imp["error"])
        self.assertIn("解释器中严禁在运行时执行 import", res_imp["error"])

        # 2. From imports
        res_imp_from = await interpreter.execute("from sys import exit")
        self.assertFalse(res_imp_from["success"])
        self.assertIn("PermissionError", res_imp_from["error"])

        # 3. Dangerous builtins bypassing
        res_eval = await interpreter.execute("eval('1 + 1')")
        self.assertFalse(res_eval["success"])
        self.assertIn("NameError", res_eval["error"])

        # 4. Hidden __class__ attribute traversal
        res_traverse = await interpreter.execute("a = 'test'; a.__class__.__subclasses__()")
        self.assertFalse(res_traverse["success"])
        self.assertIn("PermissionError", res_traverse["error"])
        self.assertIn("禁止访问私有属性/魔法方法", res_traverse["error"])

    async def test_safe_python_executor_tool_integration(self):
        """Test SafePythonExecutorTool with sandboxed workspace file operations and commands execution."""
        test_conv_id = "test_conv_ast_executor"
        workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        sandbox_dir = os.path.join(workspace_dir, "agenthub_export", test_conv_id)

        # Cleanup existing sandbox to ensure clean run safely
        if os.path.exists(sandbox_dir):
            shutil.rmtree(sandbox_dir, ignore_errors=True)
        os.makedirs(sandbox_dir, exist_ok=True)

        try:
            # Code to run inside sandbox via AST executor
            # It writes a python module, lists directory, reads it, and runs it to verify output!
            code = """
# 1. Write calculator module
file_write("calc.py", "def add(a, b):\\n    return a + b\\n")

# 2. Read file to verify content
calc_content = file_read("calc.py")
print("Calc script content:")
print(calc_content)

# 3. List sandboxed directory
files = file_list()
print("Directory files count:", len(files))

# 4. Execute python command running the script
out = run_command("python -c \\"import calc; print('Execution result:', calc.add(12, 13))\\"")
print("Command Output:")
print(out)
42
"""
            # Call tool
            tool = SafePythonExecutorTool()
            res = await tool.execute({
                "code": code,
                "conversation_id": test_conv_id
            })

            # Verify outcome
            self.assertTrue(res.success, f"Tool execution failed: {res.error}")
            self.assertEqual(res.data["result"], 42)
            stdout = res.data["stdout"]
            self.assertIn("Calc script content:", stdout)
            self.assertIn("def add(a, b):", stdout)
            self.assertTrue(any(f"Directory files count: {i}" in stdout for i in range(1, 10)))
            self.assertIn("Execution result: 25", stdout)

            # Assert file actually written to physical sandbox
            self.assertTrue(os.path.exists(os.path.join(sandbox_dir, "calc.py")))

        finally:
            # Clean up sandboxed directory safely (ignore read-only git permission errors on Windows)
            if os.path.exists(sandbox_dir):
                shutil.rmtree(sandbox_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
