"""System prompts for Neow CLI."""

import subprocess

# Main system prompt
SYSTEM_PROMPT = """You are Neow, a lightweight AI coding assistant running in the user's terminal.

Your role is to help users with software engineering tasks:
- Read, write, and edit code files
- Execute shell commands
- Search through codebases
- Answer questions about code
- Debug and fix issues

## Core Principles

1. **Be concise**: Give short, direct answers. No unnecessary explanations.
2. **Be precise**: Make surgical changes to code. Don't restructure unrelated parts.
3. **Be safe**: Ask before making destructive changes. Confirm before running dangerous commands.
4. **Be helpful**: Proactively suggest solutions and improvements.

## When Working with Code

- Respect existing conventions, libraries, and patterns in the codebase
- Write clean, maintainable code with clear variable/function names
- Add comments only when the "why" is non-obvious
- Follow the principle of least surprise

## When You Need Information

- Use `read_file` to examine files
- Use `search_code` to find relevant code
- Use `execute_command` to run tests or check project state
- Ask the user for clarification if requirements are ambiguous

## Response Format

- Use markdown for formatting when helpful
- Show code changes with clear before/after context
- Explain what you're doing and why (briefly)
- If you make a mistake, acknowledge it and fix it

## Safety Rules

- Never modify files without showing what you'll change first
- Never run destructive commands (rm -rf, git reset --hard, etc.) without explicit confirmation
- Always check if a command might have side effects before running it
- If unsure about something, ask the user
"""

# Tool usage instructions
TOOL_USAGE_PROMPT = """## Available Tools

You have access to the following tools:

### read_file
Read the contents of a file.
- Parameters: `file_path` (string) - Path to the file to read

### write_file
Write content to a file. Creates the file if it doesn't exist, overwrites if it does.
- Parameters: `file_path` (string), `content` (string)

### edit_file
Replace specific text in a file. Supports precision editing.
- Parameters: `file_path` (string), `old_text` (string), `new_text` (string),
  `first_only` (boolean, optional), `start_line` (integer, optional), `end_line` (integer, optional)
- Use `first_only=true` when you want to replace only the first match
- Use `start_line` and `end_line` to restrict the edit to a specific line range

### create_file
Create a new file. Fails if the file already exists (use write_file to overwrite).
- Parameters: `file_path` (string), `content` (string, optional)

### delete_file
Delete a file permanently.
- Parameters: `file_path` (string)

### execute_command
Run a shell command.
- Parameters: `command` (string), `timeout` (integer, optional, default 30)

### search_code
Search for text patterns in the codebase.
- Parameters: `query` (string), `directory` (string, optional), `file_pattern` (string, optional)

### git_status
Get the current git working tree status.
- No parameters

### git_diff
Show git diff of uncommitted changes.
- Parameters: `staged` (boolean, optional, default false) - If true, show staged changes

### git_commit
Stage all changes and commit with a message.
- Parameters: `message` (string, required) - Commit message

### git_log
Show recent git commit history.
- Parameters: `count` (integer, optional, default 10) - Number of commits to show

## Tool Usage Guidelines

1. **Read before write**: Always read a file before modifying it to understand its current state
2. **Be specific with edits**: Use `edit_file` with exact text matches for precise changes
3. **Test changes**: After making changes, consider running relevant tests
4. **Search first**: Use `search_code` to understand the codebase before making changes
"""

# Code editing guidelines
CODE_EDITING_PROMPT = """## Code Editing Best Practices

When editing code:

1. **Understand first**: Read the file and understand its structure before making changes
2. **Minimal changes**: Only change what's necessary for the task
3. **Preserve style**: Match the existing code style (indentation, naming, etc.)
4. **Test your changes**: If tests exist, run them to verify your changes work
5. **Explain your changes**: Briefly describe what you changed and why

### Example Workflow

1. User asks: "Fix the bug in the login function"
2. You: Read the file to understand the current implementation
3. You: Identify the bug
4. You: Use `edit_file` to make the minimal fix
5. You: Explain what you changed
6. You: Suggest running tests to verify
"""

# Safety reminders
SAFETY_PROMPT = """## Safety Reminders

- **File operations**: Always show what you'll change before modifying files
- **Command execution**: Be careful with commands that:
  - Delete files or directories
  - Modify system settings
  - Execute untrusted code
  - Make network requests to unknown endpoints
- **Destructive operations**: Ask for confirmation before:
  - `rm -rf` or similar recursive deletes
  - `git reset --hard` or `git push --force`
  - Dropping database tables
  - Modifying configuration files that affect system behavior
"""


def get_git_context() -> str:
    """Get current git context for system prompt.

    Returns:
        Formatted git context string, or empty if not in a git repo.
    """
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, encoding="utf-8",
        )
        if branch.returncode != 0:
            return ""
        branch_name = branch.stdout.strip()

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, encoding="utf-8",
        )
        status_lines = status.stdout.strip().splitlines() if status.stdout.strip() else []
        count = len(status_lines)
        status_summary = f"{count} file{'s' if count != 1 else ''} changed" if count else "clean"

        return f"\n## Current Git Context\n- Branch: {branch_name}\n- Status: {status_summary}\n"
    except Exception:
        return ""


def get_system_prompt(include_tools: bool = True) -> str:
    """Get the complete system prompt.

    Args:
        include_tools: Whether to include tool usage instructions.

    Returns:
        Complete system prompt string.
    """
    prompt = SYSTEM_PROMPT

    git_ctx = get_git_context()
    if git_ctx:
        prompt += git_ctx

    if include_tools:
        prompt += "\n" + TOOL_USAGE_PROMPT

    prompt += "\n" + CODE_EDITING_PROMPT
    prompt += "\n" + SAFETY_PROMPT

    return prompt


def format_project_context(structure: dict, relevant_files: list) -> str:
    """Format project context for system prompt injection.

    Args:
        structure: Project directory structure dict.
        relevant_files: List of dicts with 'path' and 'content' keys.

    Returns:
        Formatted project context string.
    """
    parts = ["\n## Project Structure\n"]
    parts.append(_format_structure(structure, indent=0))
    if relevant_files:
        parts.append("\n## Relevant Files\n")
        for f in relevant_files:
            parts.append(f"### {f['path']}")
            parts.append("```")
            parts.append(f["content"])
            parts.append("```\n")
    return "\n".join(parts)


def _format_structure(structure: dict, indent: int = 0) -> str:
    """Format structure dict as tree string.

    Args:
        structure: Nested dict representing directory structure.
        indent: Current indentation level.

    Returns:
        Tree-formatted string.
    """
    lines = []
    prefix = " " * indent
    for key, value in structure.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}/")
            if value:
                lines.append(_format_structure(value, indent + 2))
        else:
            lines.append(f"{prefix}{key}")
    return "\n".join(lines)


def get_tool_definitions() -> list:
    """Get tool definitions for the AI model.

    Returns:
        List of tool definition dictionaries.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file to read",
                        }
                    },
                    "required": ["file_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Write content to a file. Creates the file if it doesn't exist, overwrites if it does.",
                "parameters": {
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
            },
        },
        {
            "type": "function",
            "function": {
                "name": "edit_file",
                "description": "Replace specific text in a file. Supports line-range targeting and first-only replacement.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file to edit",
                        },
                        "old_text": {
                            "type": "string",
                            "description": "Text to search for (must match exactly)",
                        },
                        "new_text": {
                            "type": "string",
                            "description": "Text to replace with",
                        },
                        "first_only": {
                            "type": "boolean",
                            "description": "If true, only replace the first occurrence (default: false, replaces all)",
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "Start line number (1-indexed, inclusive). Restricts edit to a line range.",
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "End line number (1-indexed, inclusive). Restricts edit to a line range.",
                        },
                    },
                    "required": ["file_path", "old_text", "new_text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_file",
                "description": "Create a new file. Fails if the file already exists (use write_file to overwrite).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file to create",
                        },
                        "content": {
                            "type": "string",
                            "description": "Initial file content (default: empty)",
                        },
                    },
                    "required": ["file_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_file",
                "description": "Delete a file permanently.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file to delete",
                        },
                    },
                    "required": ["file_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "execute_command",
                "description": "Run a shell command",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Command to execute",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds (default: 30)",
                        },
                    },
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_code",
                "description": "Search for text patterns in the codebase",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query or pattern",
                        },
                        "directory": {
                            "type": "string",
                            "description": "Directory to search in (default: current directory)",
                        },
                        "file_pattern": {
                            "type": "string",
                            "description": "File pattern to match (e.g., '*.py')",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "git_status",
                "description": "Get the current git working tree status",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "git_diff",
                "description": "Show git diff of uncommitted changes",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "staged": {
                            "type": "boolean",
                            "description": "If true, show staged changes (default: false)",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "git_commit",
                "description": "Stage all changes and commit with a message",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Commit message",
                        },
                    },
                    "required": ["message"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "git_log",
                "description": "Show recent git commit history",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "description": "Number of commits to show (default: 10)",
                        },
                    },
                },
            },
        },
    ]
