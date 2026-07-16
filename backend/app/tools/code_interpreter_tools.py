"""E2B-Style Code Interpreter Tool — safe subprocess-based Python environment with visual plot capture."""

import asyncio
import logging
import re

from app.core.sandbox_manager import sandbox_manager

from .registry import AgentTool, ToolResult, register_tool

_logger = logging.getLogger("code_interpreter_tools")

logger = logging.getLogger("tool_code_interpreter_tools")

# Regular expression to extract base64-encoded visual plots
IMAGE_CAPTURE_RE = re.compile(r"\[IMAGE_OUTPUT\](.*?)\[/IMAGE_OUTPUT\]", re.DOTALL)


def prepend_visual_hook(user_code: str) -> str:
    """Prepends the matplotlib visual show monkeypatching hook to the user's code safely,

    accounting for possible docstrings or from __future__ imports.
    """
    hook = (
        "import sys\n"
        "import base64\n"
        "import io\n"
        "try:\n"
        "    import matplotlib\n"
        "    matplotlib.use('Agg')\n"
        "    import matplotlib.pyplot as plt\n"
        "    def _mock_show(*args, **kwargs):\n"
        "        buf = io.BytesIO()\n"
        "        plt.savefig(buf, format='png', bbox_inches='tight', dpi=150)\n"
        "        buf.seek(0)\n"
        "        img_b64 = base64.b64encode(buf.read()).decode('utf-8')\n"
        "        print(f'\\n[IMAGE_OUTPUT]{img_b64}[/IMAGE_OUTPUT]')\n"
        "        plt.close()\n"
        "    plt.show = _mock_show\n"
        "except Exception:\n"
        "    pass\n"
    )

    lines = user_code.splitlines(keepends=True)
    insert_idx = 0
    in_docstring = False
    docstring_char = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Handle docstrings
        if not in_docstring:
            if stripped.startswith('"""'):
                in_docstring = True
                docstring_char = '"""'
                if stripped.endswith('"""') and len(stripped) > 3:
                    in_docstring = False
                continue
            elif stripped.startswith("'''"):
                in_docstring = True
                docstring_char = "'''"
                if stripped.endswith("'''") and len(stripped) > 3:
                    in_docstring = False
                continue
        else:
            if stripped.endswith(docstring_char):
                in_docstring = False
            continue

        # Handle __future__ imports
        if stripped.startswith("from __future__"):
            insert_idx = i + 1
            continue

        # Ignore comments
        if stripped.startswith("#"):
            continue

        # If we reach any other code, stop pushing the insert index
        break

    lines.insert(insert_idx, "\n# E2B Visual Telemetry Hook\n" + hook + "\n# End of Hook\n\n")
    return "".join(lines)


class E2BPythonInterpreterTool(AgentTool):
    name = "e2b_python_interpreter"
    description = "在完全物理隔离的沙箱内安全执行任意 Python/数据科学代码，支持 Matplotlib/Pandas 绘图可视化与异常崩溃诊断自愈"
    icon = "📊"
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "要执行的 Python 代码脚本，允许使用 numpy, pandas, matplotlib 等库并调用 plt.show() 绘图。",
            },
            "conversation_id": {
                "type": "string",
                "description": "对话 ID（自动注入）",
            },
        },
        "required": ["code"],
    }

    async def execute(self, params: dict) -> ToolResult:
        code = params.get("code", "").strip()
        if not code:
            return ToolResult(success=False, error="执行代码不能为空")

        executable_code = prepend_visual_hook(code)
        try:
            result = await sandbox_manager.execute(executable_code, language="python", timeout=15)
        except Exception as e:
            return ToolResult(success=False, error=f"隔离解释器启动失败: {e}")

        stdout_raw = result.get("stdout", "")
        stderr_raw = result.get("stderr", "")

        # Pull out any embedded plots
        images = []
        for match in IMAGE_CAPTURE_RE.finditer(stdout_raw):
            b64_img = match.group(1).strip()
            if b64_img:
                images.append(b64_img)

        # Clean stdout by removing the IMAGE_OUTPUT blocks so the text output is clean for the LLM
        clean_stdout = IMAGE_CAPTURE_RE.sub("", stdout_raw).strip()
        clean_stderr = stderr_raw.strip()

        # Build execution summary
        exit_code = result.get("exit_code", -1)
        success = result.get("status") == "success"

        # If execution failed (syntax error or exception), compile a helpful traceback summary
        if not success:
            err_msg = f"代码执行崩溃 (退出码: {exit_code})。"
            if clean_stderr:
                err_msg += f"\n错误堆栈:\n{clean_stderr}"
            return ToolResult(
                success=False,
                error=err_msg,
                data={
                    "stdout": clean_stdout,
                    "stderr": clean_stderr,
                    "exit_code": exit_code,
                    "images": images
                }
            )

        summary_msg = "代码解释器执行成功"
        if images:
            summary_msg += f"！已拦截捕捉并导出 {len(images)} 幅数据科学可视化图表。"

        return ToolResult(
            success=True,
            data={
                "stdout": clean_stdout,
                "stderr": clean_stderr,
                "exit_code": exit_code,
                "images": images,
                "message": summary_msg
            }
        )


# Register on load
register_tool(E2BPythonInterpreterTool())
