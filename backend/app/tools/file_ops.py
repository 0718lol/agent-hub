"""File operations tool — sandboxed file read/write/list for agents."""

import os
import time
import logging
from .registry import AgentTool, ToolResult, register_tool

logger = logging.getLogger("tool_file_ops")

# Sandbox root directory (per-conversation isolation)
_SANDBOX_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "data", "sandbox")
os.makedirs(_SANDBOX_ROOT, exist_ok=True)

# Limits
_MAX_READ_SIZE = 50000  # 50KB max read
_MAX_WRITE_SIZE = 100000  # 100KB max write
_MAX_LIST_DEPTH = 3


def _safe_path(conversation_id: str, filepath: str) -> str | None:
    """Resolve path within sandbox, preventing directory traversal."""
    sandbox_dir = os.path.abspath(os.path.join(_SANDBOX_ROOT, conversation_id))
    os.makedirs(sandbox_dir, exist_ok=True)
    resolved = os.path.abspath(os.path.join(sandbox_dir, filepath))
    # Security: ensure resolved path is within sandbox
    if not resolved.startswith(sandbox_dir):
        return None
    return resolved


def _safe_workspace_path(conversation_id: str, filepath: str) -> str | None:
    """Resolve path within the unified agenthub_export workspace sandbox, preventing directory traversal."""
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    sandbox_dir = os.path.join(workspace_dir, "agenthub_export", conversation_id)
    os.makedirs(sandbox_dir, exist_ok=True)
    resolved = os.path.abspath(os.path.join(sandbox_dir, filepath))
    if not resolved.startswith(sandbox_dir):
        return None
    return resolved


class FileReadTool(AgentTool):
    name = "file_read"
    description = "读取沙盒中的文件内容"
    icon = "📖"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径（相对于沙盒根目录）",
            },
            "conversation_id": {
                "type": "string",
                "description": "对话 ID（自动注入）",
            },
        },
        "required": ["path"],
    }

    async def execute(self, params: dict) -> ToolResult:
        filepath = params.get("path", "").strip()
        conv_id = params.get("conversation_id", "default")

        if not filepath:
            return ToolResult(success=False, error="文件路径不能为空")

        safe = _safe_path(conv_id, filepath)
        if safe is None:
            return ToolResult(success=False, error="路径越界：不允许访问沙盒外文件")

        if not os.path.exists(safe):
            return ToolResult(success=False, error=f"文件不存在: {filepath}")
        if not os.path.isfile(safe):
            return ToolResult(success=False, error=f"不是文件: {filepath}")

        try:
            size = os.path.getsize(safe)
            if size > _MAX_READ_SIZE:
                return ToolResult(success=False, error=f"文件过大 ({size} bytes)，最大 {_MAX_READ_SIZE}")

            with open(safe, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            return ToolResult(
                success=True,
                data={"content": content, "path": filepath, "size": size},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"读取失败: {str(e)}")


class FileWriteTool(AgentTool):
    name = "file_write"
    description = "在沙盒中创建或覆写文件"
    icon = "✏️"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径（相对于沙盒根目录）",
            },
            "content": {
                "type": "string",
                "description": "要写入的文件内容",
            },
            "conversation_id": {
                "type": "string",
                "description": "对话 ID（自动注入）",
            },
        },
        "required": ["path", "content"],
    }

    async def execute(self, params: dict) -> ToolResult:
        filepath = params.get("path", "").strip()
        content = params.get("content", "")
        conv_id = params.get("conversation_id", "default")

        if not filepath:
            return ToolResult(success=False, error="文件路径不能为空")

        if len(content) > _MAX_WRITE_SIZE:
            return ToolResult(success=False, error=f"内容过大 ({len(content)} chars)，最大 {_MAX_WRITE_SIZE}")

        safe = _safe_path(conv_id, filepath)
        if safe is None:
            return ToolResult(success=False, error="路径越界：不允许访问沙盒外文件")

        try:
            os.makedirs(os.path.dirname(safe), exist_ok=True)
            with open(safe, "w", encoding="utf-8") as f:
                f.write(content)

            return ToolResult(
                success=True,
                data={"path": filepath, "size": len(content), "message": f"已写入 {filepath}"},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"写入失败: {str(e)}")


class FileListTool(AgentTool):
    name = "file_list"
    description = "列出沙盒目录结构"
    icon = "📂"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "目录路径（相对于沙盒根目录，默认为根）",
            },
            "conversation_id": {
                "type": "string",
                "description": "对话 ID（自动注入）",
            },
        },
        "required": [],
    }

    async def execute(self, params: dict) -> ToolResult:
        dirpath = params.get("path", "").strip() or "."
        conv_id = params.get("conversation_id", "default")

        safe = _safe_path(conv_id, dirpath)
        if safe is None:
            return ToolResult(success=False, error="路径越界：不允许访问沙盒外目录")

        if not os.path.exists(safe):
            return ToolResult(success=True, data={"files": [], "message": "目录为空或不存在"})

        if not os.path.isdir(safe):
            return ToolResult(success=False, error=f"不是目录: {dirpath}")

        try:
            tree = []
            for root, dirs, files in os.walk(safe):
                depth = root.replace(safe, "").count(os.sep)
                if depth >= _MAX_LIST_DEPTH:
                    dirs.clear()
                    continue
                rel_root = os.path.relpath(root, safe)
                if rel_root == ".":
                    rel_root = ""
                for f in sorted(files):
                    fpath = os.path.join(rel_root, f) if rel_root else f
                    size = os.path.getsize(os.path.join(root, f))
                    tree.append({"path": fpath, "size": size, "type": "file"})
                for d in sorted(dirs):
                    dpath = os.path.join(rel_root, d) if rel_root else d
                    tree.append({"path": dpath + "/", "type": "dir"})

            return ToolResult(
                success=True,
                data={"files": tree, "count": len(tree), "root": dirpath},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"列目录失败: {str(e)}")


# Auto-register on import
register_tool(FileReadTool())
register_tool(FileWriteTool())
register_tool(FileListTool())


class FileViewWindowedTool(AgentTool):
    name = "file_view_windowed"
    description = "以视口式滑动窗口的形式精细滚动读取沙盒中大文件的特定行区间，节省 Token"
    icon = "🔭"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径（相对于沙盒根目录）",
            },
            "start_line": {
                "type": "integer",
                "description": "要查看的起始行数（从1开始，默认为1）",
            },
            "line_count": {
                "type": "integer",
                "description": "每次查看的行数限制（默认为100行）",
            },
            "conversation_id": {
                "type": "string",
                "description": "对话 ID（自动注入）",
            },
        },
        "required": ["path"],
    }

    async def execute(self, params: dict) -> ToolResult:
        filepath = params.get("path", "").strip()
        conv_id = params.get("conversation_id", "default")
        start_line = max(int(params.get("start_line", 1)), 1)
        line_count = max(int(params.get("line_count", 100)), 1)

        if not filepath:
            return ToolResult(success=False, error="文件路径不能为空")

        safe = _safe_workspace_path(conv_id, filepath)
        if safe is None:
            return ToolResult(success=False, error="路径越界：不允许访问沙盒外文件")

        if not os.path.exists(safe):
            return ToolResult(success=False, error=f"文件不存在: {filepath}")
        if not os.path.isfile(safe):
            return ToolResult(success=False, error=f"不是文件: {filepath}")

        try:
            with open(safe, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            lines = content.splitlines()
            total_lines = len(lines)

            if total_lines == 0:
                return ToolResult(
                    success=True,
                    data={
                        "content": "",
                        "start_line": 1,
                        "end_line": 0,
                        "total_lines": 0,
                        "message": f"文件为空: {filepath}"
                    }
                )

            end_line = min(start_line + line_count - 1, total_lines)
            sliced_lines = lines[start_line - 1 : end_line]
            sliced_content = "\n".join(sliced_lines)

            # Build SWE-agent style windowed summary output
            summary_lines = [
                f"[{filepath} - 窗口化查看视口: 第 {start_line} 行到第 {end_line} 行, 文件总行数: {total_lines}]",
                "------------------------------------------------------------------"
            ]
            for idx, line in enumerate(sliced_lines, start=start_line):
                summary_lines.append(f"{idx:5d}: {line}")
            summary_lines.append("------------------------------------------------------------------")
            
            scroll_up = "[Scroll up available]" if start_line > 1 else "[Start of file]"
            scroll_down = "[Scroll down available]" if end_line < total_lines else "[End of file]"
            summary_lines.append(f"{scroll_up} | {scroll_down}")

            summary_text = "\n".join(summary_lines)

            return ToolResult(
                success=True,
                data={
                    "content": sliced_content,
                    "start_line": start_line,
                    "end_line": end_line,
                    "total_lines": total_lines,
                    "message": summary_text
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=f"读取失败: {str(e)}")


class FileEditLineTool(AgentTool):
    name = "file_edit_line"
    description = "对沙盒中的文件执行高容错、省 Token 的行级微替换编辑，并自动触发静态编译语法自检校验"
    icon = "✂️"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径（相对于沙盒根目录）",
            },
            "start_line": {
                "type": "integer",
                "description": "被替换的起始行数（从1开始，包含该行）",
            },
            "end_line": {
                "type": "integer",
                "description": "被替换的结束行数（从1开始，包含该行）",
            },
            "replacement_code": {
                "type": "string",
                "description": "用于替换该行区间的新代码内容",
            },
            "conversation_id": {
                "type": "string",
                "description": "对话 ID（自动注入）",
            },
        },
        "required": ["path", "start_line", "end_line", "replacement_code"],
    }

    async def execute(self, params: dict) -> ToolResult:
        filepath = params.get("path", "").strip()
        start_line = int(params.get("start_line"))
        end_line = int(params.get("end_line"))
        replacement_code = params.get("replacement_code", "")
        conv_id = params.get("conversation_id", "default")

        if not filepath:
            return ToolResult(success=False, error="文件路径不能为空")

        safe = _safe_workspace_path(conv_id, filepath)
        if safe is None:
            return ToolResult(success=False, error="路径越界：不允许访问沙盒外文件")

        if not os.path.exists(safe):
            return ToolResult(success=False, error=f"文件不存在: {filepath}。行替换编辑器仅适用于编辑已有文件。")

        try:
            with open(safe, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            lines = content.splitlines(keepends=True)
            total_lines = len(lines)

            # Handle edge case for completely empty file
            if total_lines == 0:
                lines = ["\n"]
                total_lines = 1

            if start_line < 1 or start_line > total_lines or end_line < 1 or end_line > total_lines or start_line > end_line:
                return ToolResult(success=False, error=f"无效的行范围: {start_line} 到 {end_line}，文件总行数: {total_lines}")

            # 1. Create pre-write git checkpoint
            workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
            sandbox_dir = os.path.join(workspace_dir, "agenthub_export", conv_id)
            os.makedirs(sandbox_dir, exist_ok=True)
            
            try:
                from app.core.git_sandbox import git_checkpoint, git_rollback
                await git_checkpoint(sandbox_dir, f"Pre-edit-line: {filepath}")
            except Exception:
                # Fallback if git is not initialized or fails
                git_checkpoint = None
                git_rollback = None

            # 2. Slice and replace lines (start_line and end_line are 1-indexed)
            replacement_lines = replacement_code.splitlines(keepends=True)
            # Ensure line ending consistency
            if replacement_lines and not replacement_lines[-1].endswith(("\n", "\r\n")):
                replacement_lines[-1] = replacement_lines[-1] + "\n"

            lines[start_line - 1 : end_line] = replacement_lines
            new_content = "".join(lines)

            # 3. Write back modified contents
            with open(safe, "w", encoding="utf-8") as f:
                f.write(new_content)

            # 4. Perform Quality Gate compiler lint check (py_compile for python)
            is_valid = True
            error_msg = ""
            if safe.endswith(".py"):
                try:
                    import py_compile
                    py_compile.compile(safe, doraise=True)
                except Exception as e:
                    is_valid = False
                    error_msg = f"Python Syntax Error: {e}"

            if not is_valid:
                # Trigger rollback immediately
                if git_rollback:
                    await git_rollback(sandbox_dir)
                else:
                    # File system backup fallback: restore original content manually if git failed
                    with open(safe, "w", encoding="utf-8") as f:
                        f.write(content)
                return ToolResult(
                    success=False,
                    error=f"❌ 代码行替换失败！检测到代码存在语法缺陷，工作空间已安全自愈回退。\n详情: {error_msg}"
                )

            # Create success git checkpoint
            if git_checkpoint:
                await git_checkpoint(sandbox_dir, f"Success-edit-line: {filepath}")

            return ToolResult(
                success=True,
                data={
                    "path": filepath,
                    "start_line": start_line,
                    "end_line": end_line,
                    "total_lines": len(lines),
                    "message": f"成功对文件 '{filepath}' 第 {start_line} 行到第 {end_line} 行执行精准行级替换且静态语法编译校验 100% 通过！"
                }
            )

        except Exception as e:
            return ToolResult(success=False, error=f"行级替换失败: {str(e)}")


register_tool(FileViewWindowedTool())
register_tool(FileEditLineTool())
