"""Built-in tool specs: schema, implementation and approval policy in one place."""

from typing import Any, List

from neow.core.approval import ApprovalTier
from neow.core.tools_registry import ToolSpec
from neow.tools.command import execute_command
from neow.tools.file_ops import (
    create_file,
    delete_file,
    edit_file,
    hashline_edit,
    read_file,
    write_file,
)
from neow.tools.fs_search import glob, grep, list_dir
from neow.tools.git import git_commit, git_diff, git_log, git_status
from neow.tools.search import search_code


def _search_code(query: str, directory: str = ".", file_pattern: str = "*") -> Any:
    """Adapter: the schema makes ``directory`` optional, the function does not."""

    return search_code(query, directory, file_pattern)


def _todo_unbound(todos: Any) -> str:
    """Placeholder: each ConversationManager binds its own ``write_todos``."""

    raise RuntimeError("todo_write is not connected to a conversation")


def builtin_specs() -> List[ToolSpec]:
    """Specs for every built-in tool, in the order the model sees them."""

    return [
        ToolSpec(
            name="read_file",
            description=(
                "Read a file as numbered lines (`  N<TAB>text`; the prefix is not "
                "part of the file). Shows up to 2000 lines; use offset/limit to "
                "page through larger files. Ends with the ¶PATH#HASH anchor for "
                "hashline_edit."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to read",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "First line to read, 1-indexed (default: 1)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines (default: 2000)",
                    },
                },
                "required": ["file_path"],
            },
            func=read_file,
            tier=ApprovalTier.READ,
            read_only=True,
        ),
        ToolSpec(
            name="write_file",
            description=(
                "Write content to a file, creating it or replacing it entirely. "
                "Replacing an existing file requires having read it first."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to write",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file",
                    },
                },
                "required": ["file_path", "content"],
            },
            func=write_file,
            tier=ApprovalTier.WRITE,
            mutates_files=True,
        ),
        ToolSpec(
            name="edit_file",
            description=(
                "Replace exact text in a file (read the file first). Optionally "
                "only the first match, or only within a line range. Returns the "
                "number of replacements."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to edit",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "Text to search for (must match " "exactly)",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "Text to replace with",
                    },
                    "first_only": {
                        "type": "boolean",
                        "description": "If true, only replace the first "
                        "occurrence (default: false, "
                        "replaces all)",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Start line number (1-indexed, "
                        "inclusive). Restricts edit to a "
                        "line range.",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "End line number (1-indexed, "
                        "inclusive). Restricts edit to a "
                        "line range.",
                    },
                },
                "required": ["file_path", "old_text", "new_text"],
            },
            func=edit_file,
            tier=ApprovalTier.WRITE,
            mutates_files=True,
        ),
        ToolSpec(
            name="create_file",
            description=(
                "Create a new file. Fails if the file already exists "
                "(use write_file to overwrite)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to create",
                    },
                    "content": {
                        "type": "string",
                        "description": "Initial file content (default: " "empty)",
                    },
                },
                "required": ["file_path"],
            },
            func=create_file,
            tier=ApprovalTier.WRITE,
            mutates_files=True,
        ),
        ToolSpec(
            name="delete_file",
            description="Delete a file permanently.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to delete",
                    }
                },
                "required": ["file_path"],
            },
            func=delete_file,
            tier=ApprovalTier.WRITE,
            mutates_files=True,
        ),
        ToolSpec(
            name="execute_command",
            description=(
                "Run a shell command and return its output. Failures return "
                "'Error: exit code N' with stdout and stderr."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to execute"},
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 120, max: 600)",
                    },
                },
                "required": ["command"],
            },
            func=execute_command,
            tier=ApprovalTier.EXEC,
        ),
        ToolSpec(
            name="grep",
            description=(
                "Search file contents for a regular expression (ripgrep when "
                "installed). Skips files ignored by git. Returns matching file "
                "paths by default; output_mode 'content' returns "
                "'path:line:text' lines, 'count' returns 'path:N'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regular expression to search for",
                    },
                    "path": {
                        "type": "string",
                        "description": "File or directory to search (default: "
                        "current directory)",
                    },
                    "glob": {
                        "type": "string",
                        "description": "Only search files matching this glob, "
                        "e.g. '*.py' or 'src/**/*.{ts,tsx}'",
                    },
                    "output_mode": {
                        "type": "string",
                        "enum": ["files_with_matches", "content", "count"],
                        "description": "What to return (default: "
                        "files_with_matches)",
                    },
                    "context": {
                        "type": "integer",
                        "description": "Lines of context around each match "
                        "(content mode only)",
                    },
                    "case_insensitive": {
                        "type": "boolean",
                        "description": "Ignore case (default: false)",
                    },
                    "head_limit": {
                        "type": "integer",
                        "description": "Maximum entries returned (default: 100)",
                    },
                },
                "required": ["pattern"],
            },
            func=grep,
            tier=ApprovalTier.READ,
            read_only=True,
        ),
        ToolSpec(
            name="glob",
            description=(
                "Find files by name pattern, e.g. '**/*.py' or 'src/*.{js,ts}'. "
                "Skips files ignored by git. Returns up to 200 paths, most "
                "recently modified first."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob relative to path; '*' stays within "
                        "a directory, '**' crosses directories",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search (default: current "
                        "directory)",
                    },
                },
                "required": ["pattern"],
            },
            func=glob,
            tier=ApprovalTier.READ,
            read_only=True,
        ),
        ToolSpec(
            name="list_dir",
            description=(
                "List a directory as an indented tree (directories end with "
                "'/'), skipping files ignored by git."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory to list (default: current "
                        "directory)",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "How many levels to show (default: 1)",
                    },
                },
            },
            func=list_dir,
            tier=ApprovalTier.READ,
            read_only=True,
        ),
        ToolSpec(
            name="search_code",
            description=(
                "Deprecated: use grep. Search files for a regex "
                "(case-insensitive) and return matches with file path, line "
                "number and line text."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query or pattern",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Directory to search in (default: "
                        "current directory)",
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "File pattern to match (e.g., " "'*.py')",
                    },
                },
                "required": ["query"],
            },
            func=_search_code,
            tier=ApprovalTier.READ,
            read_only=True,
        ),
        ToolSpec(
            name="git_status",
            description="Get the current git working tree status",
            parameters={"type": "object", "properties": {}},
            func=git_status,
            tier=ApprovalTier.READ,
            read_only=True,
        ),
        ToolSpec(
            name="git_diff",
            description="Show git diff of uncommitted changes",
            parameters={
                "type": "object",
                "properties": {
                    "staged": {
                        "type": "boolean",
                        "description": "If true, show staged changes "
                        "(default: false)",
                    }
                },
            },
            func=git_diff,
            tier=ApprovalTier.READ,
            read_only=True,
        ),
        ToolSpec(
            name="git_commit",
            description="Stage all changes and commit with a message",
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message"}
                },
                "required": ["message"],
            },
            func=git_commit,
            tier=ApprovalTier.WRITE,
        ),
        ToolSpec(
            name="git_log",
            description="Show recent git commit history",
            parameters={
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of commits to show (default: " "10)",
                    }
                },
            },
            func=git_log,
            tier=ApprovalTier.READ,
            read_only=True,
        ),
        ToolSpec(
            name="hashline_edit",
            description=(
                "Edit a file using hash-anchored line ranges. Safer than edit_file "
                "because it detects if the file was modified since it was last "
                "read. Edits are applied from bottom to top. Format: ¶PATH#HASH."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to edit",
                    },
                    "expected_hash": {
                        "type": "string",
                        "description": "Expected content hash "
                        "(8-char hex from "
                        "¶PATH#HASH). Fails if file "
                        "changed.",
                    },
                    "edits": {
                        "type": "string",
                        "description": "JSON array of edit operations. Each: "
                        '{"start_line": int, "end_line": int, '
                        '"new_content": str, "insert_before": '
                        'bool, "insert_after": bool}',
                    },
                },
                "required": ["file_path", "expected_hash", "edits"],
            },
            func=hashline_edit,
            tier=ApprovalTier.WRITE,
            mutates_files=True,
        ),
        ToolSpec(
            name="todo_write",
            description=(
                "Create or update your task list for multi-step work; each call "
                "replaces the whole list. Mark a task in_progress before starting "
                "it (only one at a time) and completed as soon as it is done. "
                "Returns the updated checklist."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "description": "The complete task list",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "content": {
                                    "type": "string",
                                    "description": "Imperative task description",
                                },
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"],
                                },
                            },
                            "required": ["content", "status"],
                        },
                    }
                },
                "required": ["todos"],
            },
            func=_todo_unbound,
            tier=ApprovalTier.NONE,
        ),
    ]


__all__ = ["builtin_specs"]
