"""Output formatting utilities for Neow CLI."""

import sys
import io
from typing import Any, Dict

from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax

# Force UTF-8 output on Windows to avoid encoding issues
if sys.platform == "win32":
    # Wrap stdout with UTF-8 encoding
    utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    console = Console(file=utf8_stdout, force_terminal=True)
else:
    console = Console()


def print_user_message(message: str) -> None:
    """Print user message with formatting.

    Args:
        message: User message to print.
    """
    console.print(f"[bold blue]You:[/bold blue] {message}")


def print_assistant_message(message: str) -> None:
    """Print assistant message with formatting.

    Args:
        message: Assistant message to print.
    """
    console.print(f"[bold green]Assistant:[/bold green] {message}")


def print_tool_call(tool_name: str, parameters: Dict[str, Any]) -> None:
    """Print tool call with formatting.

    Args:
        tool_name: Name of the tool being called.
        parameters: Tool call parameters.
    """
    console.print(f"[bold yellow]Tool Call:[/bold yellow] {tool_name}")
    console.print(f"[dim]Parameters:[/dim] {parameters}")


def print_tool_result(result: str, is_error: bool = False) -> None:
    """Print tool result with formatting.

    Args:
        result: Tool execution result.
        is_error: Whether the result is an error.
    """
    color = "red" if is_error else "green"
    console.print(f"[bold {color}]Tool Result:[/bold {color}]")
    console.print(result)


def print_code(code: str, language: str = "python") -> None:
    """Print code with syntax highlighting.

    Args:
        code: Code to print.
        language: Programming language for syntax highlighting.
    """
    syntax = Syntax(code, language, theme="monokai", line_numbers=True)
    console.print(syntax)


def print_markdown(content: str) -> None:
    """Print markdown content.

    Args:
        content: Markdown content to print.
    """
    md = Markdown(content)
    console.print(md)


def print_error(message: str) -> None:
    """Print error message.

    Args:
        message: Error message to print.
    """
    console.print(f"[bold red]Error:[/bold red] {message}")


def print_warning(message: str) -> None:
    """Print warning message.

    Args:
        message: Warning message to print.
    """
    console.print(f"[bold yellow]Warning:[/bold yellow] {message}")


def print_info(message: str) -> None:
    """Print info message.

    Args:
        message: Info message to print.
    """
    console.print(f"[bold cyan]Info:[/bold cyan] {message}")


def print_welcome() -> None:
    """Print welcome message."""
    console.print("[bold cyan]Neow CLI[/bold cyan]")
    console.print("A lightweight, general-purpose AI CLI assistant.")
    console.print()
    console.print("[bold]Commands:[/bold]")
    console.print("  /help     - Show this help message")
    console.print("  /clear    - Clear conversation history")
    console.print("  /exit     - Exit the CLI")
    console.print("  /model <name> - Switch AI model (deepseek, anthropic, openai)")
    console.print("  /diff     - Show uncommitted changes")
    console.print("  /commit [msg] - Commit changes (AI generates message if none given)")
    console.print("  /undo     - Undo last commit")
    console.print("  /add <file> - Add file to conversation context")
    console.print("  /drop <file> - Remove file from context")
    console.print("  /ls       - List context files")
    console.print("  /lint     - Run linter (use '/lint on'/'/lint off' to toggle auto-lint)")
    console.print("  /test     - Run tests (use '/test on'/'/test off' to toggle auto-test)")
    console.print("  /architect - Enter architect mode (plan + sub-agent dispatch)")
    console.print("  /code     - Return to normal coding mode")
    console.print("  /save [name] - Save session (auto-saved on exit)")
    console.print("  /load <name> - Load a saved session")
    console.print("  /history   - List saved sessions")
    console.print("  /cost      - Show token usage and cost")
    console.print("  /web <url>  - Fetch web page content into context")
    console.print("  Plugins load from ~/.neow/plugins/ on startup")
    console.print()
    console.print("[bold]Usage:[/bold]")
    console.print("  Type your message and press Enter to interact with the AI assistant.")
