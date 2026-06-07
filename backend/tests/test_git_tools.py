"""Tests for Git integration tools."""
import pytest
from unittest.mock import patch, MagicMock
from app.tools.git_tools import GitCommitTool, GitPushTool, CreatePRTool, _run_git


@pytest.fixture
def commit_tool():
    return GitCommitTool()


@pytest.fixture
def push_tool():
    return GitPushTool()


@pytest.fixture
def pr_tool():
    return CreatePRTool()


class TestRunGit:
    """Test the _run_git helper function."""

    @patch("subprocess.run")
    def test_successful_command(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123", stderr="")
        code, stdout, stderr = _run_git(["rev-parse", "HEAD"])
        assert code == 0
        assert stdout == "abc123"

    @patch("subprocess.run")
    def test_failed_command(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        code, stdout, stderr = _run_git(["status"])
        assert code == 1
        assert stderr == "error"

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_git_not_installed(self, mock_run):
        code, stdout, stderr = _run_git(["status"])
        assert code == -1
        assert "not installed" in stderr


class TestGitCommitTool:
    """Test GitCommitTool."""

    @pytest.mark.asyncio
    @patch("app.tools.git_tools._run_git")
    async def test_commit_success(self, mock_run, commit_tool):
        mock_run.side_effect = [
            (0, "", ""),  # git add
            (0, "[main abc123] test commit", ""),  # git commit
            (0, "abc123def456", ""),  # git rev-parse HEAD
        ]
        result = await commit_tool.execute(message="test commit")
        assert result["success"] is True
        assert result["commit_hash"] == "abc123def456"

    @pytest.mark.asyncio
    @patch("app.tools.git_tools._run_git")
    async def test_commit_nothing_to_commit(self, mock_run, commit_tool):
        mock_run.side_effect = [
            (0, "", ""),  # git add
            (1, "", "nothing to commit"),  # git commit
        ]
        result = await commit_tool.execute(message="test")
        assert result["success"] is True
        assert result["commit_hash"] is None

    @pytest.mark.asyncio
    async def test_commit_empty_message(self, commit_tool):
        result = await commit_tool.execute(message="")
        assert result["success"] is False
        assert "required" in result["error"]

    @pytest.mark.asyncio
    @patch("app.tools.git_tools._run_git")
    async def test_commit_with_specific_files(self, mock_run, commit_tool):
        mock_run.side_effect = [
            (0, "", ""),  # git add
            (0, "[main abc] test", ""),  # git commit
            (0, "abc123", ""),  # git rev-parse HEAD
        ]
        result = await commit_tool.execute(message="test", files=["file1.py", "file2.py"])
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_commit_rejects_traversal(self, commit_tool):
        result = await commit_tool.execute(message="test", files=["../../etc/passwd"])
        assert result["success"] is False
        assert "Invalid" in result["error"]


class TestGitPushTool:
    """Test GitPushTool."""

    @pytest.mark.asyncio
    @patch("app.tools.git_tools._run_git")
    async def test_push_success(self, mock_run, push_tool):
        mock_run.return_value = (0, "Everything up-to-date", "")
        result = await push_tool.execute()
        assert result["success"] is True

    @pytest.mark.asyncio
    @patch("app.tools.git_tools._run_git")
    async def test_push_failure(self, mock_run, push_tool):
        mock_run.return_value = (1, "", "Permission denied")
        result = await push_tool.execute()
        assert result["success"] is False
        assert "failed" in result["error"]

    @pytest.mark.asyncio
    @patch("app.tools.git_tools._run_git")
    async def test_push_specific_branch(self, mock_run, push_tool):
        mock_run.return_value = (0, "", "")
        result = await push_tool.execute(branch="feature/test")
        assert result["success"] is True
        assert result["branch"] == "feature/test"


class TestCreatePRTool:
    """Test CreatePRTool."""

    @pytest.mark.asyncio
    @patch("subprocess.run")
    @patch("app.tools.git_tools._run_git")
    async def test_create_pr_success(self, mock_run, mock_subprocess, pr_tool):
        # Mock git push
        mock_run.return_value = (0, "", "")
        # Mock gh pr create
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout="https://github.com/test/repo/pull/123",
            stderr=""
        )
        result = await pr_tool.execute(title="Test PR", body="Description")
        assert result["success"] is True
        assert "pull/123" in result["pr_url"]

    @pytest.mark.asyncio
    async def test_create_pr_empty_title(self, pr_tool):
        result = await pr_tool.execute(title="")
        assert result["success"] is False
        assert "required" in result["error"]

    @pytest.mark.asyncio
    @patch("app.tools.git_tools._run_git")
    async def test_create_pr_push_failure(self, mock_run, pr_tool):
        mock_run.side_effect = [
            (0, "feature/test", ""),  # git rev-parse --abbrev-ref HEAD
            (1, "", "Push failed"),  # git push
        ]
        result = await pr_tool.execute(title="Test PR")
        assert result["success"] is False
        assert "Push failed" in result["error"]
