"""E2B-Style Code Interpreter Tool — safe subprocess-based Python environment with visual plot capture."""

import os
import re
import sys
import logging
import subprocess
import shutil
from typing import Dict, Any
from .registry import AgentTool, ToolResult, register_tool

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
        conv_id = params.get("conversation_id", "default")

        if not code:
            return ToolResult(success=False, error="执行代码不能为空")

        # 1. Resolve sandboxed workspace directory
        workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        sandbox_dir = os.path.join(workspace_dir, "agenthub_export", conv_id)
        os.makedirs(sandbox_dir, exist_ok=True)

        # 2. Prepend the visual show monkeypatch hook
        executable_code = prepend_visual_hook(code)

        # 3. Write code to a temporary script file in sandbox
        script_file_name = f"temp_interpreter_{conv_id}.py"
        script_path = os.path.join(sandbox_dir, script_file_name)

        try:
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(executable_code)
        except IOError as ioe:
            return ToolResult(success=False, error=f"写入临时执行文件失败: {ioe}")

        # 4. Safely execute code via subprocess python runner
        # Run with a 15-second timeout to prevent denial-of-service/infinite loops
        try:
            # Explicitly use the same python interpreter running this host to ensure path and package matches
            proc = subprocess.run(
                [sys.executable, script_file_name],
                cwd=sandbox_dir,
                capture_output=True,
                text=True,
                timeout=15.0
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error="🔒 执行超时！脚本已超过最大运行上限 15 秒并被强制终止，可能存在死循环。"
            )
        finally:
            # Clean up the temporary script file to keep the sandbox clean
            if os.path.exists(script_path):
                try:
                    os.remove(script_path)
                except Exception:
                    pass

        # 5. Extract images and sanitize stdout
        stdout_raw = proc.stdout or ""
        stderr_raw = proc.stderr or ""
        
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
        exit_code = proc.returncode
        success = (exit_code == 0)

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
