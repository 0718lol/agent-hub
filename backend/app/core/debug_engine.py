"""Debug engine - automatic error analysis and code repair.

Based on: SWE-agent (Princeton) minimal-change philosophy
          + Aider diff-based editing approach
          + Agentless localize-then-repair pattern

Principles:
1. Parse errors with Python stdlib (100% accurate)
2. Minimal changes - only fix what's broken
3. Verify fixes by re-running code
4. Never break existing functionality
"""
import logging
import re
import traceback

logger = logging.getLogger("debug_engine")

# Errors that can be auto-fixed
FIXABLE_ERRORS = {
    "NameError": "add missing import or variable definition",
    "ModuleNotFoundError": "add missing package import",
    "ImportError": "fix import statement",
    "SyntaxError": "fix syntax error",
    "IndentationError": "fix indentation",
    "TabError": "fix mixed tabs and spaces",
    "TypeError": "fix argument types or count",
    "AttributeError": "fix method or property name",
    "KeyError": "check dictionary key exists",
    "IndexError": "check list index range",
    "ValueError": "fix input value",
    "UnicodeDecodeError": "fix encoding",
    "FileNotFoundError": "fix file path",
    "PermissionError": "fix file permissions",
    "OSError": "fix OS-level operation",
    "IOError": "fix I/O operation",
    "RuntimeError": "fix runtime issue",
}

# Errors that should NOT be auto-fixed (logic errors)
NOT_FIXABLE = {
    "AssertionError": "logic error, needs human review",
    "RecursionError": "infinite recursion, needs redesign",
    "MemoryError": "resource exhaustion",
    "KeyboardInterrupt": "user interrupted",
    "SystemExit": "system exit",
    "GeneratorExit": "generator cleanup",
}


def parse_error(output: str) -> dict | None:
    """Parse Python traceback to extract structured error info.
    
    Uses regex to extract error type, message, file, line number.
    Returns None if no error found.
    """
    if not output or not output.strip():
        return None

    # Check for traceback
    tb_match = re.search(
        r'Traceback \(most recent call last\):(.*?)$',
        output, re.DOTALL
    )

    if tb_match:
        tb_text = tb_match.group(1).strip()

        # Extract error type and message (last line)
        lines = [l.strip() for l in tb_text.strip().split('\n') if l.strip()]
        error_line = lines[-1] if lines else ""
        parts = error_line.split(':', 1)
        error_type = parts[0].strip()
        error_msg = parts[1].strip() if len(parts) > 1 else ""

        # Extract file and line number
        file_match = re.search(r'File "([^"]+)", line (\d+)', tb_text)
        file_name = file_match.group(1) if file_match else None
        line_num = int(file_match.group(2)) if file_match else None

        # Extract source line if available
        source_line = ""
        if file_match:
            # Source line usually follows the File line
            after_file = tb_text[file_match.end():]
            src_match = re.search(r'^\s*(.+?)$', after_file, re.MULTILINE)
            if src_match:
                source_line = src_match.group(1).strip()

    else:
        # No traceback - check for simple error messages
        error_patterns = [
            (r'(\w+Error):\s*(.+)', "error"),
            (r'Error:\s*(.+)', "error"),
            (r'FAILED:\s*(.+)', "test_failure"),
        ]
        error_type = "Unknown"
        error_msg = output[:200]
        file_name = None
        line_num = None
        source_line = ""

        for pattern, _ in error_patterns:
            match = re.search(pattern, output)
            if match:
                if len(match.groups()) == 2:
                    error_type = match.group(1)
                    error_msg = match.group(2).strip()
                else:
                    error_msg = match.group(1).strip()
                break

    fixable = error_type in FIXABLE_ERRORS and error_type not in NOT_FIXABLE

    return {
        "error_type": error_type,
        "error_msg": error_msg[:300],
        "line_num": line_num,
        "file_name": file_name,
        "source_line": source_line[:200],
        "fixable": fixable,
        "fix_hint": FIXABLE_ERRORS.get(error_type, "needs manual analysis"),
        "traceback": tb_text if tb_match else output[:500],
    }


def build_fix_prompt(error_info: dict, code: str, task: str, attempt: int = 1) -> str:
    """Build a minimal-change fix prompt.
    
    Emphasizes: only fix the specific error, don't rewrite everything.
    """
    return (
        f"任务：{task[:300]}\n\n"
        f"代码运行出错，请修复：\n"
        f"- 错误类型：{error_info['error_type']}\n"
        f"- 错误信息：{error_info['error_msg']}\n"
        f"- 出错行号：{error_info['line_num']}\n"
        f"- 修复提示：{error_info['fix_hint']}\n"
        f"- 修复尝试：第 {attempt} 次\n\n"
        f"原始代码：\n```python\n{code}\n```\n\n"
        f"【重要规则】\n"
        f"1. 只修改必要的行，不要重写整个代码\n"
        f"2. 保持原有的逻辑和结构不变\n"
        f"3. 输出修复后的完整代码，用 ```python 包裹\n"
        f"4. 不要解释，只输出代码"
    )


def build_analysis_prompt(error_info: dict, code: str) -> str:
    """Build a root cause analysis prompt (for complex errors)."""
    return (
        f"分析以下错误的根本原因，用一句话总结：\n\n"
        f"错误类型：{error_info['error_type']}\n"
        f"错误信息：{error_info['error_msg']}\n"
        f"出错行号：{error_info['line_num']}\n"
        f"出错代码：{error_info.get('source_line', '')}\n\n"
        f"代码片段（前 50 行）：\n```python\n{code[:2000]}\n```\n\n"
        f"格式：[原因] 你的分析"
    )


def extract_code_block(text: str) -> str | None:
    """Extract Python code block from LLM response."""
    match = re.search(r'```(?:python)?\n(.*?)```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: if response looks like code (has def/import/class)
    if any(kw in text for kw in ['def ', 'import ', 'class ', 'return ']):
        return text.strip()
    return None
