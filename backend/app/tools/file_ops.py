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
