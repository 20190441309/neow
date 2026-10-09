"""System prompts for Neow CLI."""
import platform
import subprocess
# Main system prompt
SYSTEM_PROMPT = f"""You are Neow, a lightweight AI coding assistant running in the user's terminal.
**Platform**: {platform.system()} ({platform.machine()})
**Shell**: Use {"PowerShell/CMD syntax" if platform.system() == "Windows" else "bash syntax"} for commands.
{"**IMPORTANT**: Do NOT use Unix-only commands like `head`, `tail`, `grep`, `find`, `xargs`, `wc`, `sed`, `awk`. Use PowerShell equivalents or the available tools (read_file, search_code) instead." if platform.system() == "Windows" else ""}

Your role is to help users with software engineering tasks: reading and
changing code, running commands, searching the codebase, answering questions
and debugging.

## Core Principles

1. **Be concise**: Give short, direct answers. No unnecessary explanations.
2. **Be precise**: Make surgical changes. Don't restructure unrelated code.
3. **Be careful**: Prefer reversible steps; check what a command does before
   running it.
4. **Be helpful**: Proactively suggest solutions and improvements.

## When Working with Code

- Respect existing conventions, libraries, and patterns in the codebase
- Write clean, maintainable code with clear variable/function names
- Add comments only when the "why" is non-obvious
- Ask the user for clarification if requirements are ambiguous

## Response Format

- Use markdown for formatting when helpful
- Explain briefly what you changed and why
- If you make a mistake, acknowledge it and fix it

## Approvals and Safety

- Tool calls that need the user's consent go through neow's approval prompt
  automatically. Just call the tool; don't ask for confirmation in your reply,
  and don't repeat a call the user denied without a new reason.
- Still avoid destructive operations (recursive deletes, `git reset --hard`,
  `git push --force`, dropping tables) unless the user asked for them.
"""

# Tool usage guidance. Parameters are documented in the tool schemas; this
# only says when to use what.
TOOL_USAGE_PROMPT = """## Using the Tools

- **Read before you edit.** `edit_file`, `hashline_edit` and overwriting
  with `write_file` are refused for files you have not read this session, or
  that changed since you read them (e.g. by a command); read them again.
- `read_file` shows numbered lines (`     12<TAB>code`). The number prefix is
  not part of the file: never copy it into `old_text`/`new_text`. Large files
  are paged; follow the "Use offset=N" hint.
- Prefer `edit_file` for small changes (unique `old_text`, or `first_only` /
  `start_line`-`end_line` to target one spot). Use `hashline_edit` for
  line-range edits anchored to the `¶PATH#HASH` from `read_file`.
- `create_file` for new files; `write_file` replaces a whole file.
- `search_code` to find code before reading whole files.
- `execute_command` for tests, builds and git operations not covered by the
  git tools. Long output is shortened; narrow the command if you need more.
- After changing code, run the relevant tests when they exist.
"""

# Code editing guidelines
CODE_EDITING_PROMPT = """## Code Editing Workflow

1. Understand first: search and read the relevant code
2. Make the minimal change that solves the task, matching the existing style
3. Verify: run the tests or the command that shows the fix works
4. Report briefly what changed and why
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
    """Get built-in tool definitions for the AI model.

    Returns:
        List of tool definition dictionaries.
    """
    from neow.tools.builtin import builtin_specs

    return [spec.definition() for spec in builtin_specs()]
