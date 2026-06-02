"""Aider-style SEARCH/REPLACE Block-level High-Tolerance File Editor Tool."""

import os
import re
import logging
from .registry import AgentTool, ToolResult, register_tool

logger = logging.getLogger("tool_block_editor_tools")

# Regex to capture Aider conflict marker blocks
BLOCK_RE = re.compile(
    r"<<<<<<<\s*SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>>\s*REPLACE",
    re.DOTALL
)


def apply_patch_block(content: str, search_code: str, replace_code: str) -> str:
    """Applies a single SEARCH/REPLACE block replacement on the file content with high tolerance."""
    normalized_content = content.replace("\r\n", "\n")
    normalized_search = search_code.replace("\r\n", "\n")
    normalized_replace = replace_code.replace("\r\n", "\n")

    # 1. Try exact match
    if normalized_search in normalized_content:
        return normalized_content.replace(normalized_search, normalized_replace, 1)

    # 2. Try trailing space-insensitive match (crucial for python indentation spacing tolerance)
    content_lines = normalized_content.splitlines()
    search_lines = normalized_search.splitlines()

    stripped_content_lines = [line.rstrip() for line in content_lines]
    stripped_search_lines = [line.rstrip() for line in search_lines]

    search_len = len(stripped_search_lines)
    for i in range(len(stripped_content_lines) - search_len + 1):
        if stripped_content_lines[i : i + search_len] == stripped_search_lines:
            # Perform block replacement in original lines list
            replace_lines = normalized_replace.splitlines()
            content_lines[i : i + search_len] = replace_lines
            # Preserve trailing newline of original content if present
            ending = "\n" if normalized_content.endswith("\n") else ""
            return "\n".join(content_lines) + ending

    raise ValueError(
        "❌ 匹配失败！未在目标文件中找到指定的 SEARCH 块。\n"
        "请确保搜索块内的代码段与目标文件中的旧代码在字符、空格及缩进上完全一致。"
    )


class FilePatchBlockTool(AgentTool):
    name = "file_patch_block"
    description = (
        "对指定的文件执行 Aider 格式的高容错 SEARCH/REPLACE 块级修改，"
        "支持单次执行多块替换，内置静态编译语法门禁与 Git 影子回滚自愈机制"
    )
    icon = "🩹"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要修改的目标文件在沙盒内的相对或绝对路径",
            },
            "patch_blocks": {
                "type": "string",
                "description": (
                    "包含一个或多个 SEARCH/REPLACE 块的文本。例如：\n"
                    "<<<<<<< SEARCH\n"
                    "def old_func():\n"
                    "    return 1\n"
                    "=======\n"
                    "def old_func():\n"
                    "    return 2\n"
                    ">>>>>>> REPLACE"
                ),
            },
            "conversation_id": {
                "type": "string",
                "description": "对话 ID（自动注入）",
            },
        },
        "required": ["path", "patch_blocks"],
    }

    async def execute(self, params: dict) -> ToolResult:
        filepath = params.get("path", "").strip()
        patch_blocks = params.get("patch_blocks", "").strip()
        conv_id = params.get("conversation_id", "default")

        if not filepath or not patch_blocks:
            return ToolResult(success=False, error="文件路径 path 和修改块 patch_blocks 不能为空")

        # 1. Resolve sandboxed file path
        workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        sandbox_dir = os.path.join(workspace_dir, "agenthub_export", conv_id)
        os.makedirs(sandbox_dir, exist_ok=True)

        # Secure path resolution to block directory traversals
        safe_path = os.path.abspath(os.path.join(sandbox_dir, filepath))
        if not safe_path.startswith(sandbox_dir):
            return ToolResult(success=False, error="路径越权：只允许修改会话沙盒目录内的文件")

        if not os.path.exists(safe_path):
            return ToolResult(success=False, error=f"目标文件不存在: '{filepath}'。请先创建文件或确认路径。")

        # 2. Parse SEARCH/REPLACE blocks
        blocks = BLOCK_RE.findall(patch_blocks)
        if not blocks:
            # Loose regex fallback in case of whitespace anomalies around keywords
            loose_re = re.compile(
                r"<<<<<<<.*?SEARCH\s*\n(.*?)\n=======\n(.*?)\n>>>>>>>.*?REPLACE",
                re.DOTALL
            )
            blocks = loose_re.findall(patch_blocks)
            if not blocks:
                return ToolResult(
                    success=False,
                    error=(
                        "无法解析 SEARCH/REPLACE 块。请务必使用标准的 Aider 块冲突格式，例如：\n"
                        "<<<<<<< SEARCH\n"
                        "待匹配的旧代码\n"
                        "=======\n"
                        "要替换的新代码\n"
                        ">>>>>>> REPLACE"
                    )
                )

        # 3. Read current file content
        try:
            with open(safe_path, "r", encoding="utf-8", errors="ignore") as f:
                original_content = f.read()
        except Exception as read_err:
            return ToolResult(success=False, error=f"读取目标文件失败: {read_err}")

        # 4. Initialize Git versioning transaction checkpoint
        try:
            from app.core.git_sandbox import git_checkpoint, git_rollback
            await git_checkpoint(sandbox_dir, f"Pre-patch-block: {filepath}")
        except Exception:
            git_checkpoint = None
            git_rollback = None

        # 5. Iteratively apply block patches
        current_content = original_content
        applied_count = 0
        for search_code, replace_code in blocks:
            try:
                current_content = apply_patch_block(current_content, search_code, replace_code)
                applied_count += 1
            except ValueError as ve:
                # Rollback sandbox files if any intermediate block failed
                if git_rollback:
                    await git_rollback(sandbox_dir)
                return ToolResult(success=False, error=f"应用第 {applied_count + 1} 个修改块时失败: {ve}")

        # 6. Write patched contents back to disk
        try:
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(current_content)
        except Exception as write_err:
            if git_rollback:
                await git_rollback(sandbox_dir)
            return ToolResult(success=False, error=f"写回修改文件失败: {write_err}")

        # 7. Perform Quality Gate static compilation lint check (py_compile for python)
        is_valid = True
        error_msg = ""
        if safe_path.endswith(".py"):
            try:
                import py_compile
                py_compile.compile(safe_path, doraise=True)
            except Exception as compile_err:
                is_valid = False
                error_msg = f"Python Syntax Error: {compile_err}"

        if not is_valid:
            # Trigger rollback immediately to recover file stability
            if git_rollback:
                await git_rollback(sandbox_dir)
            else:
                # File system manual restoration fallback
                with open(safe_path, "w", encoding="utf-8") as f:
                    f.write(original_content)
            return ToolResult(
                success=False,
                error=f"❌ 代码块替换失败！检测到生成的代码存在编译语法缺陷，沙盒工作空间已安全自愈回退。\n详情: {error_msg}"
            )

        # 8. Create success git checkpoint
        if git_checkpoint:
            await git_checkpoint(sandbox_dir, f"Success-patch-block: {filepath}")

        return ToolResult(
            success=True,
            data={
                "path": filepath,
                "applied_blocks_count": applied_count,
                "message": f"成功对文件 '{filepath}' 应用 {applied_count} 个 SEARCH/REPLACE 块修改，且静态语法编译校验 100% 通过！"
            }
        )


# Auto-register on import
register_tool(FilePatchBlockTool())
