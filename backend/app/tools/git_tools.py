"""Git integration tools for Agent workflow.

Provides git_commit, git_push, and create_pr tools that Agents can use
inside an isolated tenant conversation sandbox workspace.
"""
from __future__ import annotations

import logging
import os
import subprocess

from app.core.workspace import resolve_workspace
from app.tools.registry import AgentTool, ToolResult, register_tool

logger = logging.getLogger("git_tools")

# Fallback directory used only when direct unit tests call execute() without conversation_id
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _resolve_cwd(conversation_id: str | None) -> str | None:
    if not conversation_id:
        return None
    ws = resolve_workspace(conversation_id)
    if ws is None:
        return None
    os.makedirs(str(ws), exist_ok=True)
    return str(ws)


def _to_tool_result(raw: dict) -> ToolResult:
    return ToolResult(
        success=bool(raw.get("success")),
        data=raw,
        error=str(raw.get("error") or ""),
    )


def _run_git(args: list[str], cwd: str | None = None, timeout: int = 30) -> tuple[int, str, str]:
    """Run a git command safely. Returns (returncode, stdout, stderr)."""
    cmd = ["git"] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Git command timed out"
    except FileNotFoundError:
        return -1, "", "Git not installed"
    except Exception as e:
        return -1, "", str(e)


class GitCommitTool(AgentTool):
    """Commit code changes to git."""
    name = "git_commit"
    description = "Stage and commit files to the conversation workspace git repository"
    parameters = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Commit message",
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Files to stage (default: all changes)",
            },
            "conversation_id": {
                "type": "string",
                "description": "Conversation ID (auto-injected)",
            },
        },
        "required": ["message"],
    }

    async def validate_and_execute(self, params: dict) -> ToolResult:
        conv_id = str(params.get("conversation_id") or "").strip()
        if not conv_id:
            return ToolResult(success=False, error="conversation_id is required for workspace git operations")
        raw = await self.execute(
            message=str(params.get("message") or ""),
            files=params.get("files"),
            conversation_id=conv_id,
        )
        return _to_tool_result(raw)

    async def execute(
        self,
        message: str = "",
        files: list[str] | None = None,
        conversation_id: str | None = None,
    ) -> dict:
        """Stage files and commit."""
        if isinstance(message, dict):
            return (await self.validate_and_execute(message)).data
        if not message or not message.strip():
            return {"success": False, "error": "Commit message is required"}

        cwd = _resolve_cwd(conversation_id)
        if conversation_id and cwd is None:
            return {"success": False, "error": "Invalid conversation workspace"}

        if files:
            for f in files:
                if ".." in f or f.startswith("/"):
                    return {"success": False, "error": f"Invalid file path: {f}"}
            stage_args = ["add"] + files
        else:
            stage_args = ["add", "."]

        code, _stdout, stderr = _run_git(stage_args, cwd=cwd)
        if code != 0:
            return {"success": False, "error": f"git add failed: {stderr}"}

        code, stdout, stderr = _run_git(["commit", "-m", message], cwd=cwd)
        if code != 0:
            if "nothing to commit" in stderr or "nothing to commit" in stdout:
                return {"success": True, "message": "Nothing to commit", "commit_hash": None}
            return {"success": False, "error": f"git commit failed: {stderr}"}

        code, hash_out, _ = _run_git(["rev-parse", "HEAD"], cwd=cwd)
        commit_hash = hash_out if code == 0 else "unknown"

        logger.info(f"Git commit: {commit_hash[:8]} - {message}")
        return {
            "success": True,
            "commit_hash": commit_hash,
            "message": message,
        }


class GitPushTool(AgentTool):
    """Push commits to remote."""
    name = "git_push"
    description = "Push committed changes from conversation workspace to remote repository"
    parameters = {
        "type": "object",
        "properties": {
            "branch": {
                "type": "string",
                "description": "Branch to push (default: current branch)",
            },
            "conversation_id": {
                "type": "string",
                "description": "Conversation ID (auto-injected)",
            },
        },
    }

    async def validate_and_execute(self, params: dict) -> ToolResult:
        conv_id = str(params.get("conversation_id") or "").strip()
        if not conv_id:
            return ToolResult(success=False, error="conversation_id is required for workspace git operations")
        raw = await self.execute(
            branch=params.get("branch"),
            conversation_id=conv_id,
        )
        return _to_tool_result(raw)

    async def execute(
        self,
        branch: str | None = None,
        conversation_id: str | None = None,
    ) -> dict:
        """Push to remote."""
        if isinstance(branch, dict):
            return (await self.validate_and_execute(branch)).data
        cwd = _resolve_cwd(conversation_id)
        if conversation_id and cwd is None:
            return {"success": False, "error": "Invalid conversation workspace"}

        args = ["push"]
        if branch:
            args.extend(["origin", branch])
        else:
            args.extend(["origin", "HEAD"])

        code, _stdout, stderr = _run_git(args, cwd=cwd, timeout=60)
        if code != 0:
            return {"success": False, "error": f"git push failed: {stderr}"}

        logger.info(f"Git push: {branch or 'current branch'}")
        return {"success": True, "branch": branch or "current"}


class CreatePRTool(AgentTool):
    """Create a GitHub Pull Request."""
    name = "create_pr"
    description = "Create a Pull Request on GitHub for the conversation workspace"
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "PR title",
            },
            "body": {
                "type": "string",
                "description": "PR body/description",
            },
            "branch": {
                "type": "string",
                "description": "Source branch (default: current branch)",
            },
            "base": {
                "type": "string",
                "description": "Target branch (default: main)",
            },
            "conversation_id": {
                "type": "string",
                "description": "Conversation ID (auto-injected)",
            },
        },
        "required": ["title"],
    }

    async def validate_and_execute(self, params: dict) -> ToolResult:
        conv_id = str(params.get("conversation_id") or "").strip()
        if not conv_id:
            return ToolResult(success=False, error="conversation_id is required for workspace git operations")
        raw = await self.execute(
            title=str(params.get("title") or ""),
            body=str(params.get("body") or ""),
            branch=params.get("branch"),
            base=str(params.get("base") or "main"),
            conversation_id=conv_id,
        )
        return _to_tool_result(raw)

    async def execute(
        self,
        title: str = "",
        body: str = "",
        branch: str | None = None,
        base: str = "main",
        conversation_id: str | None = None,
    ) -> dict:
        """Create a PR using GitHub CLI (gh)."""
        if isinstance(title, dict):
            return (await self.validate_and_execute(title)).data
        if not title or not title.strip():
            return {"success": False, "error": "PR title is required"}

        cwd = _resolve_cwd(conversation_id)
        if conversation_id and cwd is None:
            return {"success": False, "error": "Invalid conversation workspace"}

        if not branch:
            code, branch_out, _ = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
            if code != 0:
                return {"success": False, "error": "Could not determine current branch"}
            branch = branch_out

        push_result = await GitPushTool().execute(branch=branch, conversation_id=conversation_id)
        if not push_result.get("success"):
            return {"success": False, "error": f"Push failed: {push_result.get('error')}"}

        try:
            cmd = ["gh", "pr", "create", "--title", title, "--body", body or "", "--base", base, "--head", branch]
            result = subprocess.run(cmd, cwd=cwd or PROJECT_ROOT, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return {"success": False, "error": f"PR creation failed: {result.stderr.strip()}"}

            pr_url = result.stdout.strip()
            logger.info(f"PR created: {pr_url}")
            return {"success": True, "pr_url": pr_url}
        except FileNotFoundError:
            return {"success": False, "error": "GitHub CLI (gh) not installed"}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "PR creation timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Auto-register tools
register_tool(GitCommitTool())
register_tool(GitPushTool())
register_tool(CreatePRTool())
