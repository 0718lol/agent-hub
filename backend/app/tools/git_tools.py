"""Git integration tools for Agent workflow.

Provides git_commit, git_push, and create_pr tools that Agents can use
to commit code, push to remote, and create Pull Requests.
"""
import asyncio
import logging
import os
import subprocess

from app.tools.registry import AgentTool, register_tool

logger = logging.getLogger("git_tools")

# Project root directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _run_git(args: list[str], cwd: str = None, timeout: int = 30) -> tuple[int, str, str]:
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
    description = "Stage and commit files to git repository"
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
        },
        "required": ["message"],
    }

    async def execute(self, message: str, files: list[str] = None) -> dict:
        """Stage files and commit."""
        if not message or not message.strip():
            return {"success": False, "error": "Commit message is required"}

        # Stage files
        if files:
            # Validate file paths (no traversal)
            for f in files:
                if ".." in f or f.startswith("/"):
                    return {"success": False, "error": f"Invalid file path: {f}"}
            stage_args = ["add"] + files
        else:
            stage_args = ["add", "."]

        code, stdout, stderr = _run_git(stage_args)
        if code != 0:
            return {"success": False, "error": f"git add failed: {stderr}"}

        # Commit
        code, stdout, stderr = _run_git(["commit", "-m", message])
        if code != 0:
            if "nothing to commit" in stderr or "nothing to commit" in stdout:
                return {"success": True, "message": "Nothing to commit", "commit_hash": None}
            return {"success": False, "error": f"git commit failed: {stderr}"}

        # Get commit hash
        code, hash_out, _ = _run_git(["rev-parse", "HEAD"])
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
    description = "Push committed changes to remote repository"
    parameters = {
        "type": "object",
        "properties": {
            "branch": {
                "type": "string",
                "description": "Branch to push (default: current branch)",
            },
        },
    }

    async def execute(self, branch: str = None) -> dict:
        """Push to remote."""
        args = ["push"]
        if branch:
            args.extend(["origin", branch])
        else:
            args.extend(["origin", "HEAD"])

        code, stdout, stderr = _run_git(args, timeout=60)
        if code != 0:
            return {"success": False, "error": f"git push failed: {stderr}"}

        logger.info(f"Git push: {branch or 'current branch'}")
        return {"success": True, "branch": branch or "current"}


class CreatePRTool(AgentTool):
    """Create a GitHub Pull Request."""
    name = "create_pr"
    description = "Create a Pull Request on GitHub"
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
        },
        "required": ["title"],
    }

    async def execute(self, title: str, body: str = "", branch: str = None, base: str = "main") -> dict:
        """Create a PR using GitHub CLI (gh)."""
        if not title or not title.strip():
            return {"success": False, "error": "PR title is required"}

        # Get current branch if not specified
        if not branch:
            code, branch_out, _ = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
            if code != 0:
                return {"success": False, "error": "Could not determine current branch"}
            branch = branch_out

        # Push first
        push_result = await GitPushTool().execute(branch)
        if not push_result.get("success"):
            return {"success": False, "error": f"Push failed: {push_result.get('error')}"}

        # Create PR using gh CLI
        try:
            cmd = ["gh", "pr", "create", "--title", title, "--body", body or "", "--base", base, "--head", branch]
            result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30)
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
