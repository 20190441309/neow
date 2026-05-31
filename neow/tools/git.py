"""Git integration tools for Neow CLI."""

import subprocess
from pathlib import Path

from neow.utils.logger import logger


class GitError(Exception):
    """Git operation error."""

    pass


def _run_git(args: list[str], cwd: str | None = None) -> str:
    """Run a git command and return output.

    Args:
        args: Git command arguments (without 'git' prefix).
        cwd: Working directory. Defaults to current directory.

    Returns:
        Command output as string.

    Raises:
        GitError: If command fails.
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
        return result.stdout.strip()
    except FileNotFoundError:
        raise GitError("Git is not installed or not in PATH")
    except GitError:
        raise
    except Exception as e:
        raise GitError(f"Git command failed: {e}")


def git_status() -> str:
    """Get git working tree status.

    Returns:
        Formatted status string.

    Raises:
        GitError: If not a git repo or command fails.
    """
    output = _run_git(["status", "--porcelain"])
    if not output:
        return "Working tree clean"
    lines = output.splitlines()
    modified = sum(1 for l in lines if l.startswith(" M") or l.startswith("M"))
    added = sum(1 for l in lines if l.startswith("A"))
    deleted = sum(1 for l in lines if l.startswith(" D") or l.startswith("D"))
    untracked = sum(1 for l in lines if l.startswith("??"))
    parts = []
    if modified:
        parts.append(f"{modified} modified")
    if added:
        parts.append(f"{added} added")
    if deleted:
        parts.append(f"{deleted} deleted")
    if untracked:
        parts.append(f"{untracked} untracked")
    return f"Changes: {', '.join(parts)}\n{output}"


def git_diff(staged: bool = False) -> str:
    """Show git diff.

    Args:
        staged: If True, show staged changes.

    Returns:
        Diff output.

    Raises:
        GitError: If command fails.
    """
    args = ["diff", "--staged"] if staged else ["diff"]
    return _run_git(args)


def git_log(count: int = 10) -> str:
    """Show recent git log.

    Args:
        count: Number of commits to show.

    Returns:
        Log output.

    Raises:
        GitError: If command fails.
    """
    return _run_git(["log", "--oneline", f"-n{count}"])


def git_commit(message: str) -> str:
    """Stage all changes and commit.

    Args:
        message: Commit message.

    Returns:
        Commit confirmation.

    Raises:
        GitError: If command fails.
    """
    _run_git(["add", "-A"])
    output = _run_git(["commit", "-m", message])
    return output


def git_undo() -> str:
    """Undo the last commit (soft reset).

    Returns:
        Confirmation message.

    Raises:
        GitError: If no commits to undo.
    """
    _run_git(["reset", "--soft", "HEAD~1"])
    return "Undone last commit (changes kept in staging)"


def auto_commit(file_path: str, action: str = "edit") -> str:
    """Auto-commit after file change. Called programmatically.

    Args:
        file_path: Path of the changed file.
        action: Action type (write_file, edit_file, create_file, delete_file).

    Returns:
        Commit result.

    Raises:
        GitError: If commit fails.
    """
    path = Path(file_path).name
    return git_commit(f"neow: {action} {path}")
