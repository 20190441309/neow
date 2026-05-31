"""Output formatting utilities for Neow CLI."""

import sys
import io
import re
from typing import Any, Dict, Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.markup import escape
from rich.panel import Panel
from rich.align import Align
from rich.text import Text
from rich.table import Table

# Force UTF-8 output on Windows to avoid encoding issues
if sys.platform == "win32":
    utf8_stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )
    console = Console(file=utf8_stdout, force_terminal=True)
else:
    console = Console()


# ── Feature 1: ASCII Logo ──────────────────────────────────────────

LOGO_ART = r"""
[bold cyan]
   _   _                     _____
  | \ | |                   |  _  \
  |  \| | ___  ___  ___ ___ | | | |_____      __
  |     |/ _ \/ __|/ __/ _ \| | | / _ \ \ /\ / /
  | |\  | (_) \__ \ (_| (_) | |/ / (_) \ V  V /
  \_| \_/\___/|___/\___\___/|___/ \___/ \_/\_/
[/bold cyan]"""


def make_logo(model: str = "", version: str = "0.5") -> str:
    """Create startup logo with model info.

    Args:
        model: Current model name.
        version: Neow version.

    Returns:
        Formatted logo string.
    """
    buf = io.StringIO()
    tmp = Console(file=buf, force_terminal=True, width=60)

    tmp.print(LOGO_ART)

    info_parts = [f"[dim]v{version}[/dim]"]
    if model:
        info_parts.append(f"[bold green]{model}[/bold green]")
    info_parts.append("[dim]Ready[/dim]")
    info_line = " · ".join(info_parts)
    tmp.print(Align.center(info_line))
    tmp.print()

    return buf.getvalue()


def print_logo(model: str = "", version: str = "0.5") -> None:
    """Print startup logo to console."""
    console.print(LOGO_ART)
    info_parts = [f"[dim]v{version}[/dim]"]
    if model:
        info_parts.append(f"[bold green]{model}[/bold green]")
    info_parts.append("[dim]Ready[/dim]")
    info_line = " · ".join(info_parts)
    console.print(Align.center(info_line))
    console.print()


# ── Feature 2: Conversation Panels ────────────────────────────────


def _looks_like_markdown(text: str) -> bool:
    """Quick heuristic to detect markdown content."""
    patterns = [
        r"^#{1,6}\s",  # headings
        r"^\* ",  # bullet list
        r"^- ",  # bullet list
        r"^\d+\. ",  # numbered list
        r"```",  # code fence
        r"\[.+\]\(.+\)",  # links
        r"^\|.+\|",  # tables
    ]
    for line in text.split("\n"):
        stripped = line.strip()
        for p in patterns:
            if re.match(p, stripped):
                return True
    return False


def format_user_panel(message: str) -> Panel:
    """Format user message as a panel.

    Args:
        message: User message text.

    Returns:
        Rich Panel object.
    """
    return Panel(
        message,
        title="[bold blue]You[/bold blue]",
        border_style="blue",
        padding=(0, 1),
    )


def format_assistant_panel(message: str) -> Panel:
    """Format assistant message as a panel.

    Args:
        message: Assistant message text.

    Returns:
        Rich Panel object.
    """
    content = Markdown(message) if _looks_like_markdown(message) else message
    return Panel(
        content,
        title="[bold green]Neow[/bold green]",
        border_style="green",
        padding=(0, 1),
    )


def print_user_message(message: str) -> None:
    """Print user message with panel formatting."""
    console.print(format_user_panel(message))


def print_assistant_message(message: str) -> None:
    """Print assistant message with panel formatting."""
    console.print(format_assistant_panel(message))


# ── Feature 3: Tool Call Panels ───────────────────────────────────

TOOL_ICONS = {
    "read_file": "\U0001f4d6",
    "write_file": "✏️",
    "edit_file": "✏️",
    "create_file": "\U0001f4c4",
    "delete_file": "\U0001f5d1️",
    "execute_command": "⚡",
    "search_code": "\U0001f50d",
    "grep_code": "\U0001f50d",
    "git_status": "\U0001f33f",
    "git_diff": "\U0001f4ca",
    "git_commit": "\U0001f4be",
    "git_log": "\U0001f4dc",
    "hashline_edit": "🔗",
}

def format_tool_call_panel(tool_name: str, parameters: Dict[str, Any]) -> Panel:
    """Format tool call as a compact panel.

    Args:
        tool_name: Name of the tool.
        parameters: Tool call parameters.

    Returns:
        Rich Panel object.
    """
    icon = TOOL_ICONS.get(tool_name, "\U0001f527")

    param_lines = []
    for key, value in parameters.items():
        val_str = str(value)
        if len(val_str) > 80:
            val_str = val_str[:77] + "..."
        param_lines.append(f"  [dim]{key}:[/dim] {val_str}")

    content = "\n".join(param_lines) if param_lines else "[dim]no parameters[/dim]"

    return Panel(
        content,
        title=f"[bold yellow]{icon} {tool_name}[/bold yellow]",
        border_style="yellow",
        padding=(0, 1),
    )


def format_tool_result_panel(result: str, is_error: bool = False) -> Panel:
    """Format tool result as a compact panel.

    Args:
        result: Tool execution result.
        is_error: Whether the result is an error.

    Returns:
        Rich Panel object.
    """
    border = "red" if is_error else "dim"
    icon = "✗" if is_error else "✓"
    title_color = "red" if is_error else "green"

    display = result
    if len(display) > 500:
        display = display[:497] + "..."

    return Panel(
        display,
        title=f"[bold {title_color}]{icon} Result[/bold {title_color}]",
        border_style=border,
        padding=(0, 1),
    )


def print_tool_call(tool_name: str, parameters: Dict[str, Any]) -> None:
    """Print tool call with panel formatting."""
    console.print(format_tool_call_panel(tool_name, parameters))


def print_tool_result(result: str, is_error: bool = False) -> None:
    """Print tool result with panel formatting."""
    console.print(format_tool_result_panel(result, is_error))


# ── Feature 4: Status Bar ─────────────────────────────────────────


def create_status_bar(
    model: str,
    tokens_used: int = 0,
    tokens_max: int = 128000,
    cost: float = 0.0,
    branch: str = "",
) -> str:
    """Create a status bar string.

    Args:
        model: Current model name.
        tokens_used: Tokens used so far.
        tokens_max: Max token context window.
        cost: Cumulative cost.
        branch: Current git branch.

    Returns:
        Formatted status bar string.
    """
    pct = int(tokens_used / tokens_max * 100) if tokens_max > 0 else 0
    bar_width = 20
    filled = int(bar_width * pct / 100)
    bar = "█" * filled + "░" * (bar_width - filled)

    parts = [
        f" {model}",
        f" ctx: {tokens_used:,}/{tokens_max:,} [{bar}] {pct}%",
        f" cost: ${cost:.4f}",
    ]
    if branch:
        parts.append(f" {branch}")
    parts.append(" /help")

    return "│".join(parts)


def print_status_bar(
    model: str,
    tokens_used: int = 0,
    tokens_max: int = 128000,
    cost: float = 0.0,
    branch: str = "",
) -> None:
    """Print status bar to console."""
    bar_text = create_status_bar(model, tokens_used, tokens_max, cost, branch)
    width = console.width or 80
    console.print(f"[dim]{'─' * width}[/dim]")
    console.print(f"[dim]{bar_text}[/dim]")


# ── Feature 5: Thinking Spinner ───────────────────────────────────
# (Handled via Rich Status context manager in repl.py)


# ── Feature 3b: Approval Panel ──────────────────────────────────────


def format_approval_panel(tool_name: str, parameters: Dict[str, Any], reason: str) -> Panel:
    """Format an approval request as a visually distinct panel.

    Args:
        tool_name: Name of the tool requiring approval.
        parameters: Tool parameters dict.
        reason: Why approval is needed.

    Returns:
        Rich Panel object.
    """
    lines = [f"[bold]{escape(reason)}[/bold]"]
    if tool_name == "execute_command":
        lines.append(f"  [dim]Command:[/dim] {escape(str(parameters.get('command', '')))}")
    elif "file_path" in parameters:
        lines.append(f"  [dim]File:[/dim] {escape(str(parameters.get('file_path', '')))}")
        if "content" in parameters:
            content = str(parameters["content"])
            preview = content[:80] + "..." if len(content) > 80 else content
            lines.append(f"  [dim]Content:[/dim] {escape(preview)}")
        elif "old_text" in parameters:
            lines.append(f"  [dim]Replace:[/dim] {escape(str(parameters.get('old_text', ''))[:60])}")
    lines.append("")
    lines.append("[bold][Y][/bold] 允许   [bold][N][/bold] 拒绝   [dim](单键选择，无需回车)[/dim]")
    return Panel(
        "\n".join(lines),
        title="[bold magenta]⚠ Approval Required[/bold magenta]",
        border_style="magenta",
        padding=(0, 1),
    )

def print_approval_request(tool_name: str, parameters: Dict[str, Any], reason: str) -> None:
    """Print approval request with panel formatting."""
    console.print(format_approval_panel(tool_name, parameters, reason))


def format_reasoning_dropdown(reasoning: str) -> Panel:
    """Format reasoning content as a collapsed dropdown panel.

    Shows only a summary header, hinting that /think will expand it.

    Args:
        reasoning: The full reasoning/thinking text.

    Returns:
        Rich Panel object.
    """
    lines = reasoning.count("\n") + 1
    chars = len(reasoning)

    summary = (
        f"[dim]Thought for {lines} lines ({chars:,} chars) · "
        f"[bold]/think[/bold] to expand[/dim]"
    )
    return Panel(
        summary,
        title="[bold dim]💭 Thinking[/bold dim]",
        border_style="dim",
        padding=(0, 1),
    )


def format_reasoning_expanded(reasoning: str) -> Panel:
    """Format reasoning content as an expanded panel.

    Args:
        reasoning: The full reasoning/thinking text.

    Returns:
        Rich Panel object.
    """
    return Panel(
        reasoning,
        title="[bold dim]💭 Thinking[/bold dim]",
        border_style="dim",
        padding=(0, 1),
    )


# ── Feature 6 & 8: Streaming + Markdown ──────────────────────────


def render_markdown(content: str) -> Markdown:
    """Render markdown content as Rich Markdown object.

    Args:
        content: Markdown text.

    Returns:
        Rich Markdown object.
    """
    return Markdown(content)


def print_markdown(content: str) -> None:
    """Print markdown content."""
    console.print(Markdown(content))


# ── Feature 7: Diff Coloring ─────────────────────────────────────


def format_diff(diff_text: str):
    """Format diff text with syntax highlighting.

    Args:
        diff_text: Raw diff output.

    Returns:
        Rich Syntax or Text object with diff highlighting.
    """
    if not diff_text or not diff_text.strip():
        return Text("[dim]No changes[/dim]")

    return Syntax(diff_text, "diff", theme="monokai", line_numbers=False)


def print_diff(diff_text: str) -> None:
    """Print diff with syntax highlighting."""
    if not diff_text or not diff_text.strip():
        console.print("[dim]No uncommitted changes[/dim]")
        return
    syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
    console.print(syntax)


# ── Legacy / Utility Helpers ──────────────────────────────────────


def print_code(code: str, language: str = "python") -> None:
    """Print code with syntax highlighting."""
    syntax = Syntax(code, language, theme="monokai", line_numbers=True)
    console.print(syntax)


def print_error(message: str) -> None:
    """Print error message."""
    console.print(
        Panel(
            f"[bold red]{escape(message)}[/bold red]",
            title="[bold red]Error[/bold red]",
            border_style="red",
            padding=(0, 1),
        )
    )


def print_warning(message: str) -> None:
    """Print warning message."""
    console.print(f"[bold yellow]Warning:[/bold yellow] {escape(message)}")


def print_info(message: str) -> None:
    """Print info message."""
    console.print(f"[bold cyan]Info:[/bold cyan] {message}")


def print_welcome(model: str = "") -> None:
    """Print welcome message with logo and command table.

    Args:
        model: Current model name to display in logo line.
    """
    print_logo(model=model)

    table = Table(
        show_header=True, header_style="bold", box=None, padding=(0, 2)
    )
    table.add_column("Command", style="cyan", width=20)
    table.add_column("Description")

    commands = [
        ("/help", "Show this help message"),
        ("/clear", "Clear conversation history"),
        ("/exit", "Exit the CLI"),
        ("/model <name>", "Switch AI model (deepseek, anthropic, openai)"),
        ("/diff", "Show uncommitted changes"),
        ("/commit [msg]", "Commit changes (AI generates message if none)"),
        ("/undo", "Undo last commit"),
        ("/add <file>", "Add file to conversation context"),
        ("/drop <file>", "Remove file from context"),
        ("/ls", "List context files"),
        ("/lint", "Run linter ('/lint on'/'/lint off' to toggle)"),
        ("/test", "Run tests ('/test on'/'/test off' to toggle)"),
        ("/architect", "Enter architect mode"),
        ("/code", "Return to normal coding mode"),
        ("/save [name]", "Save session"),
        ("/load <name>", "Load a saved session"),
        ("/history", "List saved sessions"),
        ("/cost", "Show token usage and cost"),
        ("/web <url>", "Fetch web page content into context"),
    ]

    for cmd, desc in commands:
        table.add_row(cmd, desc)

    console.print(table)
    console.print()
    console.print("[dim]Type your message and press Enter to interact.[/dim]")
    console.print()
