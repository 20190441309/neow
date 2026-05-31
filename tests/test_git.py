"""Tests for git tools."""

import subprocess

import pytest

from neow.tools.git import (
    git_status,
    git_diff,
    git_log,
    git_commit,
    git_undo,
    auto_commit,
    GitError,
)


def _init_repo(tmp_path):
    """Initialize a git repo in tmp_path."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(tmp_path), capture_output=True, check=True,
    )


def _make_commit(tmp_path, filename="test.txt", content="hello", message="init"):
    """Create a file and commit it."""
    (tmp_path / filename).write_text(content)
    subprocess.run(["git", "add", filename], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(tmp_path), capture_output=True, check=True,
    )


class TestGitTools:
    """Tests for git tool functions."""

    def test_git_status_empty_repo(self, tmp_path):
        """Test status on clean repo."""
        _init_repo(tmp_path)
        import os
        os.chdir(str(tmp_path))
        result = git_status()
        assert "clean" in result.lower()

    def test_git_status_with_changes(self, tmp_path):
        """Test status with untracked files."""
        _init_repo(tmp_path)
        (tmp_path / "new.txt").write_text("content")
        import os
        os.chdir(str(tmp_path))
        result = git_status()
        assert "untracked" in result.lower() or "new.txt" in result

    def test_git_diff_no_changes(self, tmp_path):
        """Test diff on clean repo."""
        _init_repo(tmp_path)
        _make_commit(tmp_path)
        import os
        os.chdir(str(tmp_path))
        result = git_diff()
        assert result == ""

    def test_git_diff_with_changes(self, tmp_path):
        """Test diff with modifications."""
        _init_repo(tmp_path)
        _make_commit(tmp_path, content="original")
        (tmp_path / "test.txt").write_text("modified")
        import os
        os.chdir(str(tmp_path))
        result = git_diff()
        assert "modified" in result

    def test_git_diff_staged(self, tmp_path):
        """Test staged diff."""
        _init_repo(tmp_path)
        _make_commit(tmp_path, content="original")
        (tmp_path / "test.txt").write_text("staged change")
        subprocess.run(["git", "add", "test.txt"], cwd=str(tmp_path), capture_output=True)
        import os
        os.chdir(str(tmp_path))
        result = git_diff(staged=True)
        assert "staged change" in result

    def test_git_commit(self, tmp_path):
        """Test committing changes."""
        _init_repo(tmp_path)
        (tmp_path / "test.txt").write_text("content")
        import os
        os.chdir(str(tmp_path))
        result = git_commit("test commit")
        assert "test commit" in result or "1 file" in result

    def test_git_log(self, tmp_path):
        """Test git log."""
        _init_repo(tmp_path)
        _make_commit(tmp_path, message="first commit")
        _make_commit(tmp_path, filename="b.txt", content="b", message="second commit")
        import os
        os.chdir(str(tmp_path))
        result = git_log()
        assert "second commit" in result
        assert "first commit" in result

    def test_git_log_with_count(self, tmp_path):
        """Test git log with count limit."""
        _init_repo(tmp_path)
        for i in range(5):
            _make_commit(tmp_path, filename=f"f{i}.txt", content=str(i), message=f"commit {i}")
        import os
        os.chdir(str(tmp_path))
        result = git_log(count=3)
        lines = [l for l in result.splitlines() if l.strip()]
        assert len(lines) <= 3

    def test_git_undo(self, tmp_path):
        """Test undoing last commit."""
        _init_repo(tmp_path)
        _make_commit(tmp_path)
        _make_commit(tmp_path, filename="b.txt", content="b", message="second")
        import os
        os.chdir(str(tmp_path))
        result = git_undo()
        assert "undone" in result.lower()

    def test_git_undo_no_commits(self, tmp_path):
        """Test undo with no commits."""
        _init_repo(tmp_path)
        import os
        os.chdir(str(tmp_path))
        with pytest.raises(GitError):
            git_undo()

    def test_auto_commit(self, tmp_path):
        """Test auto-commit after file change."""
        _init_repo(tmp_path)
        _make_commit(tmp_path)
        (tmp_path / "new.py").write_text("print('hello')")
        import os
        os.chdir(str(tmp_path))
        result = auto_commit("new.py", action="create_file")
        assert "new.py" in result

    def test_not_a_git_repo(self, tmp_path):
        """Test error when not in a git repo."""
        import os
        os.chdir(str(tmp_path))
        with pytest.raises(GitError):
            git_status()
