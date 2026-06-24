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
from rich.theme import Theme
from rich import box


# ── Theme System ───────────────────────────────────────────────────
#
# All visual styling is expressed as semantic tokens (``role.*``, ``sev.*``,
# ``accent.*``) and resolved through a Rich ``Theme``.  To re-skin the UI,
# override these tokens — no need to touch individual formatter functions.
#
# Token naming convention:
#   role.<name>            — title/label style for a chat role
#   role.<name>.border     — panel border style for that role
#   role.<name>.result_border / .error_border — variant borders
#   sev.<level>            — severity text style (info/warn/error/success)
#   accent.<purpose>       — small decorative accents (model name, version)


NEOW_THEME = Theme({
    # ── User (the human) ───────────────────────────────────────────
    "role.user":              "bold cyan",
    "role.user.border":       "cyan",

    # ── Assistant (Neow) ───────────────────────────────────────────
    "role.assistant":         "bold spring_green2",
    "role.assistant.border":  "spring_green2",

    # ── Tool calls ─────────────────────────────────────────────────
    "role.tool":              "bold gold1",
    "role.tool.border":       "gold1",
    "role.tool.result_border":"dim",
    "role.tool.error_border": "red",
    "role.tool.result_title": "bold green",
    "role.tool.error_title":  "bold red",

    # ── Approval (interactive prompt) ─────────────────────────────
    "role.approval":          "bold magenta",
    "role.approval.border":   "magenta",

    # ── Reasoning / thinking ──────────────────────────────────────
    "role.reasoning":         "bold dim",
    "role.reasoning.border":  "dim",

    # ── Severity levels ───────────────────────────────────────────
    "sev.info":               "bold cyan",
    "sev.warn":               "bold gold1",
    "sev.error":              "bold red",
    "sev.success":            "bold green",

    # ── Accent / decorative ───────────────────────────────────────
    "accent.model":           "bold green",
    "accent.version":         "dim",
    "accent.ready":           "dim",
    "status.bar":             "dim",
})


# Syntax highlighting theme used by ``print_code`` / ``print_diff``.
# Switchable at runtime via ``set_syntax_theme()``.
SYNTAX_THEME = "monokai"


def set_syntax_theme(name: str) -> None:
    """Switch the syntax-highlighting theme used by code/diff renderers.

    Args:
        name: Any Pygments theme name, e.g. ``"monokai"``, ``"dracula"``,
            ``"nord-darker"``, ``"github-dark"``.
    """
    global SYNTAX_THEME
    SYNTAX_THEME = name


def get_syntax_theme() -> str:
    """Return the currently active syntax-highlighting theme."""
    return SYNTAX_THEME


def _make_console() -> Console:
    """Build the module-level Console with UTF-8 + Neow theme applied."""
    if sys.platform == "win32":
        utf8_stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        return Console(file=utf8_stdout, force_terminal=True, theme=NEOW_THEME)
    return Console(theme=NEOW_THEME)


# Force UTF-8 output on Windows to avoid encoding issues
console = _make_console()


# ── Responsive layout helpers ─────────────────────────────────────
#
# Below this column count the UI switches to a denser layout: shorter value
# previews, fewer columns in tables, compact status bar.  80 is the
# traditional narrow-terminal threshold; most modern terminals are wider.
NARROW_TERMINAL_WIDTH = 80


def _terminal_width() -> int:
    """Return the current console width (fallback 80 if undetectable).

    Guards against mocked or non-integer ``console.width`` values (e.g. when
    tests patch ``console`` with a ``MagicMock``) by coercing through ``int``
    and falling back to ``NARROW_TERMINAL_WIDTH`` on any error.
    """
    try:
        w = console.width
        w = int(w)
        return w if w > 0 else NARROW_TERMINAL_WIDTH
    except (TypeError, ValueError, AttributeError):
        return NARROW_TERMINAL_WIDTH


def _is_narrow() -> bool:
    """True when the terminal is below ``NARROW_TERMINAL_WIDTH`` columns."""
    return _terminal_width() < NARROW_TERMINAL_WIDTH


def _adaptive_limit(default: int, narrow: int) -> int:
    """Pick a truncation limit based on current terminal width.

    Args:
        default: Limit used on normal/wide terminals.
        narrow:  Limit used when ``_is_narrow()`` is True.

    Returns:
        The appropriate char limit for the current terminal.
    """
    return narrow if _is_narrow() else default


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
    tmp = Console(file=buf, force_terminal=True, width=60, theme=NEOW_THEME)

    tmp.print(LOGO_ART)

    info_parts = [f"[accent.version]v{version}[/accent.version]"]
    if model:
        info_parts.append(f"[accent.model]{model}[/accent.model]")
    info_parts.append("[accent.ready]Ready[/accent.ready]")
    info_line = " · ".join(info_parts)
    tmp.print(Align.center(info_line))
    tmp.print()

    return buf.getvalue()


def print_logo(model: str = "", version: str = "0.5") -> None:
    """Print startup logo to console."""
    console.print(LOGO_ART)
    info_parts = [f"[accent.version]v{version}[/accent.version]"]
    if model:
        info_parts.append(f"[accent.model]{model}[/accent.model]")
    info_parts.append("[accent.ready]Ready[/accent.ready]")
    info_line = " · ".join(info_parts)
    console.print(Align.center(info_line))
    console.print()


# ── Feature 2: Conversation Panels ────────────────────────────────


def _looks_like_markdown(text: str) -> bool:
    """Quick heuristic to detect markdown content.

    Returns True if any line matches a common markdown construct: ATX
    headings, bullet/numbered lists, fenced code blocks, links, tables,
    blockquotes, or bold/italic emphasis.  Used to decide whether a message
    should go through Rich's Markdown renderer or be printed as plain text.
    """
    # Line-anchored patterns (matched at start of each stripped line).
    anchored = [
        r"^#{1,6}\s",         # ATX headings
        r"^\* ",               # bullet list (asterisk)
        r"^- ",                # bullet list (hyphen)
        r"^\+ ",               # bullet list (plus)
        r"^\d+\.\s",           # numbered list
        r"^```",               # fenced code block
        r"^\|.+\|",            # table row
        r"^>\s",               # blockquote
    ]
    # Anywhere-in-line patterns (searched, not anchored — so inline code /
    # bold that appears mid-sentence is still detected).
    inline = [
        r"\[.+\]\(.+\)",       # inline link
        r"`.+`",               # inline code
        r"\*\*.+\*\*",         # bold (asterisk)
        r"__.+__",             # bold (underscore)
    ]
    for line in text.split("\n"):
        stripped = line.strip()
        for p in anchored:
            if re.match(p, stripped):
                return True
        for p in inline:
            if re.search(p, stripped):
                return True
    return False


def _make_markdown(content: str) -> Markdown:
    """Build a Rich ``Markdown`` object that honours the active syntax theme.

    Rich's ``Markdown`` defaults to ``monokai`` for fenced code blocks and
    ignores the module-level ``SYNTAX_THEME``.  Centralising construction here
    means every assistant message / ``print_markdown`` call picks up the
    theme configured via :func:`set_syntax_theme` (and any future global
    Markdown options).

    Args:
        content: Markdown text.

    Returns:
        A Rich ``Markdown`` renderable using ``SYNTAX_THEME`` for code blocks.
    """
    return Markdown(content, code_theme=SYNTAX_THEME)


def _now_timestamp() -> str:
    """Return current local time as ``HH:MM:SS``."""
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S")


def _build_role_title(role_label: str, role_style: str, msg_num: Optional[int]) -> str:
    """Build a panel title like ``Neow #4`` (drops the number when None)."""
    if msg_num is None:
        return f"[{role_style}]{role_label}[/{role_style}]"
    return f"[{role_style}]{role_label}[/{role_style}] [dim]#{msg_num}[/dim]"


def format_user_panel(
    message: str,
    msg_num: Optional[int] = None,
    timestamp: Optional[str] = None,
) -> Panel:
    """Format user message as a panel.

    Args:
        message: User message text.
        msg_num: Optional 1-based sequence number shown in the title.
        timestamp: Optional ``HH:MM:SS`` string shown as subtitle.

    Returns:
        Rich Panel object.
    """
    return Panel(
        message,
        title=_build_role_title("You", "role.user", msg_num),
        subtitle=f"[dim]{timestamp}[/dim]" if timestamp else None,
        border_style="role.user.border",
        box=box.SQUARE,
        padding=(0, 1),
    )


def format_assistant_panel(
    message: str,
    msg_num: Optional[int] = None,
    timestamp: Optional[str] = None,
) -> Panel:
    """Format assistant message as a panel.

    Args:
        message: Assistant message text.
        msg_num: Optional 1-based sequence number shown in the title.
        timestamp: Optional ``HH:MM:SS`` string shown as subtitle.

    Returns:
        Rich Panel object.
    """
    content = _make_markdown(message) if _looks_like_markdown(message) else message
    return Panel(
        content,
        title=_build_role_title("Neow", "role.assistant", msg_num),
        subtitle=f"[dim]{timestamp}[/dim]" if timestamp else None,
        border_style="role.assistant.border",
        box=box.ROUNDED,
        padding=(0, 1),
    )


def format_streaming_assistant_panel(
    content: str,
    msg_num: Optional[int] = None,
    timestamp: Optional[str] = None,
) -> Panel:
    """Format a streaming assistant panel using plain text (no Markdown parsing).

    Used inside a Rich ``Live`` region while tokens are arriving — keeps each
    update cheap.  When the segment finishes, call ``format_assistant_panel()``
    for the final Markdown-aware render.

    Args:
        content: Buffered streaming text so far.
        msg_num: Optional 1-based sequence number shown in the title.
        timestamp: Optional ``HH:MM:SS`` string shown as subtitle.

    Returns:
        Rich Panel object with plain-text body.
    """
    return Panel(
        content,
        title=_build_role_title("Neow", "role.assistant", msg_num),
        subtitle=f"[dim]{timestamp}[/dim]" if timestamp else None,
        border_style="role.assistant.border",
        box=box.ROUNDED,
        padding=(0, 1),
    )


def print_user_message(
    message: str,
    msg_num: Optional[int] = None,
    timestamp: Optional[str] = None,
) -> None:
    """Print user message with panel formatting."""
    console.print(format_user_panel(message, msg_num=msg_num, timestamp=timestamp))


def print_assistant_message(
    message: str,
    msg_num: Optional[int] = None,
    timestamp: Optional[str] = None,
) -> None:
    """Print assistant message with panel formatting."""
    console.print(format_assistant_panel(message, msg_num=msg_num, timestamp=timestamp))


def print_turn_separator() -> None:
    """Print a thin dim horizontal rule between conversation turns.

    Used to visually delineate one user→assistant exchange from the next so
    long conversations remain scannable.
    """
    width = console.width or 80
    console.print(f"[dim]{'─' * width}[/dim]")


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

# Per-tool priority list of parameter names to surface in the collapsed
# one-line summary.  When none of the listed keys are present, the formatter
# falls back to the first parameter in the dict.
TOOL_SUMMARY_KEYS: Dict[str, list] = {
    "read_file":       ["file_path", "path"],
    "write_file":      ["file_path", "path"],
    "edit_file":       ["file_path", "path"],
    "create_file":     ["file_path", "path"],
    "delete_file":     ["file_path", "path"],
    "execute_command": ["command", "cmd"],
    "search_code":     ["pattern", "query", "regex"],
    "grep_code":       ["pattern", "query", "regex"],
    "git_commit":      ["message", "msg"],
    "hashline_edit":   ["file_path", "path"],
    "web":             ["url"],
}

# Max length of a value shown in the collapsed summary line.  Longer values
# are truncated with an ellipsis so a single tool call never wraps.
_SUMMARY_VALUE_MAX = 60


def _truncate(value: str, limit: int) -> str:
    """Truncate ``value`` to ``limit`` chars, appending ``...`` if cut."""
    if len(value) > limit:
        return value[: limit - 3] + "..."
    return value


def _tool_summary_line(tool_name: str, parameters: Dict[str, Any]) -> str:
    """Build a single-line summary for a tool call (collapsed mode).

    Picks the most relevant parameter per ``TOOL_SUMMARY_KEYS`` and truncates
    long values.  Returns ``[dim](no args)[/dim]`` when there are no params.
    The truncation limit shrinks on narrow terminals so the summary stays on
    one line.
    """
    if not parameters:
        return "[dim](no args)[/dim]"

    preferred = TOOL_SUMMARY_KEYS.get(tool_name, [])
    chosen_key: Optional[str] = None
    for k in preferred:
        if k in parameters:
            chosen_key = k
            break
    if chosen_key is None:
        # Fall back to the first parameter (stable dict ordering on 3.7+).
        chosen_key = next(iter(parameters))

    val_str = str(parameters[chosen_key]).replace("\n", " ")
    val_str = _truncate(val_str, _adaptive_limit(default=_SUMMARY_VALUE_MAX, narrow=30))
    return f"[dim]{chosen_key}:[/dim] {val_str}"


def format_tool_call_panel(
    tool_name: str,
    parameters: Dict[str, Any],
    verbose: bool = False,
) -> Panel:
    """Format tool call as a compact panel.

    In collapsed mode (default, ``verbose=False``) the panel body is a single
    one-line summary showing the tool's most relevant parameter, so multiple
    tool calls stay scannable.  In verbose mode all parameters are listed.

    Args:
        tool_name: Name of the tool.
        parameters: Tool call parameters.
        verbose: When True, list every parameter instead of a one-line summary.

    Returns:
        Rich Panel object.
    """
    icon = TOOL_ICONS.get(tool_name, "\U0001f527")
    title = f"[role.tool]{icon} {tool_name}[/role.tool]"

    if verbose:
        param_lines = []
        verbose_limit = _adaptive_limit(default=80, narrow=40)
        for key, value in parameters.items():
            val_str = str(value)
            if len(val_str) > verbose_limit:
                val_str = val_str[: verbose_limit - 3] + "..."
            param_lines.append(f"  [dim]{key}:[/dim] {val_str}")
        content = "\n".join(param_lines) if param_lines else "[dim]no parameters[/dim]"
    else:
        content = _tool_summary_line(tool_name, parameters)

    return Panel(
        content,
        title=title,
        border_style="role.tool.border",
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
    if is_error:
        border = "role.tool.error_border"
        icon = "✗"
        title_style = "role.tool.error_title"
    else:
        border = "role.tool.result_border"
        icon = "✓"
        title_style = "role.tool.result_title"

    display = result
    result_limit = _adaptive_limit(default=500, narrow=200)
    if len(display) > result_limit:
        display = display[: result_limit - 3] + "..."

    return Panel(
        display,
        title=f"[{title_style}]{icon} Result[/{title_style}]",
        border_style=border,
        padding=(0, 1),
    )


def print_tool_call(
    tool_name: str,
    parameters: Dict[str, Any],
    verbose: bool = False,
) -> None:
    """Print tool call with panel formatting.

    Args:
        tool_name: Name of the tool.
        parameters: Tool call parameters.
        verbose: When True, expand all parameters instead of a one-line summary.
    """
    console.print(format_tool_call_panel(tool_name, parameters, verbose=verbose))


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
    bar_width = _adaptive_limit(default=20, narrow=8)
    filled = int(bar_width * pct / 100)
    bar = "█" * filled + "░" * (bar_width - filled)

    parts = [f" {model}"]

    if _is_narrow():
        # Compact: just model + pct, drop the bar/cost/branch to fit ~80 cols.
        parts.append(f" {pct}%")
    else:
        parts.append(f" ctx: {tokens_used:,}/{tokens_max:,} [{bar}] {pct}%")
        parts.append(f" cost: ${cost:.4f}")
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
    console.print(f"[status.bar]{'─' * width}[/status.bar]")
    console.print(f"[status.bar]{bar_text}[/status.bar]")


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
        cmd_limit = _adaptive_limit(default=120, narrow=60)
        cmd = escape(str(parameters.get('command', '')))
        lines.append(f"  [dim]Command:[/dim] {_truncate(cmd, cmd_limit)}")
    elif "file_path" in parameters:
        lines.append(f"  [dim]File:[/dim] {escape(str(parameters.get('file_path', '')))}")
        if "content" in parameters:
            content = str(parameters["content"])
            content_limit = _adaptive_limit(default=80, narrow=40)
            preview = _truncate(content, content_limit)
            lines.append(f"  [dim]Content:[/dim] {escape(preview)}")
        elif "old_text" in parameters:
            replace_limit = _adaptive_limit(default=60, narrow=30)
            lines.append(
                f"  [dim]Replace:[/dim] {escape(_truncate(str(parameters.get('old_text', '')), replace_limit))}"
            )
    lines.append("")
    lines.append("[dim]用 [bold]↑/↓/←/→[/bold] 选择 · [bold]Enter[/bold] 确认 · 或按 [bold]Y/N[/bold] 快捷键[/dim]")
    return Panel(
        "\n".join(lines),
        title="[role.approval]⚠ Approval Required[/role.approval]",
        border_style="role.approval.border",
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
        title="[role.reasoning]💭 Thinking[/role.reasoning]",
        border_style="role.reasoning.border",
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
        title="[role.reasoning]💭 Thinking[/role.reasoning]",
        border_style="role.reasoning.border",
        padding=(0, 1),
    )


# ── Feature 6 & 8: Streaming + Markdown ──────────────────────────


def render_markdown(content: str) -> Markdown:
    """Render markdown content as Rich Markdown object.

    Args:
        content: Markdown text.

    Returns:
        Rich Markdown object using the active syntax theme for code blocks.
    """
    return _make_markdown(content)


def print_markdown(content: str) -> None:
    """Print markdown content."""
    console.print(_make_markdown(content))


# ── Feature 7: Diff Coloring ─────────────────────────────────────


# Diff lexer token styles (semantic, theme-independent).
_DIFF_ADD_STYLE     = "bold green"
_DIFF_DEL_STYLE     = "bold red"
_DIFF_HUNK_STYLE    = "bold cyan"
_DIFF_META_STYLE    = "dim"
_DIFF_CONTEXT_STYLE = "dim"


def _colorize_diff_lines(diff_text: str) -> Text:
    """Render a unified diff as a Rich ``Text`` with per-line semantic colors.

    Unlike Pygments' diff lexer (whose colours depend on ``SYNTAX_THEME``),
    this paints each line by its leading marker so additions/removals/hunk
    headers stay high-contrast regardless of the active theme:

    * ``+`` lines  → green (additions)
    * ``-`` lines  → red   (deletions)
    * ``@@`` lines → cyan  (hunk headers)
    * ``diff --git`` / ``index`` / ``+++`` / ``---`` → dim (file metadata)
    * everything else → dim (context lines)

    Args:
        diff_text: Raw unified diff text.

    Returns:
        A Rich ``Text`` with style spans applied per line.
    """
    text = Text()
    for i, line in enumerate(diff_text.split("\n")):
        if i > 0:
            text.append("\n")
        if line.startswith("+++") or line.startswith("---"):
            text.append(line, style=_DIFF_META_STYLE)
        elif line.startswith("diff ") or line.startswith("index ") or line.startswith("Index:"):
            text.append(line, style=_DIFF_META_STYLE)
        elif line.startswith("@@"):
            text.append(line, style=_DIFF_HUNK_STYLE)
        elif line.startswith("+"):
            text.append(line, style=_DIFF_ADD_STYLE)
        elif line.startswith("-"):
            text.append(line, style=_DIFF_DEL_STYLE)
        else:
            text.append(line, style=_DIFF_CONTEXT_STYLE)
    return text


def _split_diff(diff_text: str) -> Table:
    """Build a before/after side-by-side Table from a unified diff.

    For each hunk line the original (``-``) goes in the left column and the
    new (``+``) goes in the right; context lines appear in both; hunk headers
    span both columns.

    Args:
        diff_text: Raw unified diff text.

    Returns:
        A Rich ``Table`` with ``Old`` / ``New`` columns.
    """
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Old", style="red", width=None)
    table.add_column("New", style="green", width=None)

    old_buf: list = []
    new_buf: list = []

    def flush() -> None:
        """Emit the buffered old/new lines as one row, padding the shorter."""
        if not old_buf and not new_buf:
            return
        n = max(len(old_buf), len(new_buf))
        for i in range(n):
            o = old_buf[i] if i < len(old_buf) else ""
            nw = new_buf[i] if i < len(new_buf) else ""
            table.add_row(o, nw)
        old_buf.clear()
        new_buf.clear()

    for line in diff_text.split("\n"):
        if line.startswith("+++") or line.startswith("---") or \
           line.startswith("diff ") or line.startswith("index ") or \
           line.startswith("Index:"):
            flush()
            table.add_row(Text(line, style=_DIFF_META_STYLE),
                          Text(line, style=_DIFF_META_STYLE))
        elif line.startswith("@@"):
            flush()
            table.add_row(Text(line, style=_DIFF_HUNK_STYLE),
                          Text(line, style=_DIFF_HUNK_STYLE))
        elif line.startswith("+"):
            new_buf.append(Text(line, style=_DIFF_ADD_STYLE))
        elif line.startswith("-"):
            old_buf.append(Text(line, style=_DIFF_DEL_STYLE))
        else:
            # Context line goes to both sides.
            ctx = Text(line, style=_DIFF_CONTEXT_STYLE)
            old_buf.append(ctx)
            new_buf.append(ctx)
    flush()
    return table


def format_diff(diff_text: str, split: bool = False):
    """Format diff text with semantic per-line highlighting.

    By default returns a Rich ``Text`` where each line is coloured by its
    diff marker (+/=/@@/metadata), giving high-contrast additions/removals
    independent of the active syntax theme.  When ``split=True`` returns a
    side-by-side ``Table`` (Old | New) instead.

    Args:
        diff_text: Raw unified diff output.
        split: When True, render as a before/after two-column table.

    Returns:
        Rich ``Text`` (inline mode), ``Table`` (split mode), or ``Text``
        holding a "No changes" placeholder when input is empty.
    """
    if not diff_text or not diff_text.strip():
        return Text("[dim]No changes[/dim]")

    if split:
        return _split_diff(diff_text)
    return _colorize_diff_lines(diff_text)


def print_diff(diff_text: str, split: bool = False) -> None:
    """Print diff with semantic per-line highlighting.

    Args:
        diff_text: Raw unified diff output.
        split: When True, render as a before/after two-column table.
    """
    if not diff_text or not diff_text.strip():
        console.print("[dim]No uncommitted changes[/dim]")
        return
    console.print(format_diff(diff_text, split=split))


# ── Legacy / Utility Helpers ──────────────────────────────────────


def print_code(code: str, language: str = "python") -> None:
    """Print code with syntax highlighting."""
    syntax = Syntax(code, language, theme=SYNTAX_THEME, line_numbers=True)
    console.print(syntax)


def print_error(message: str) -> None:
    """Print error message."""
    console.print(
        Panel(
            f"[sev.error]{escape(message)}[/sev.error]",
            title="[sev.error]Error[/sev.error]",
            border_style="role.tool.error_border",
            padding=(0, 1),
        )
    )


def print_warning(message: str) -> None:
    """Print warning message."""
    console.print(f"[sev.warn]Warning:[/sev.warn] {escape(message)}")


def print_info(message: str) -> None:
    """Print info message."""
    console.print(f"[sev.info]Info:[/sev.info] {message}")


def print_welcome(
    model: str = "",
    recent_sessions: Optional[list] = None,
) -> None:
    """Print welcome message with logo, grouped command cards, and recent sessions.

    Args:
        model: Current model name to display in logo line.
        recent_sessions: Optional list of session metadata dicts
            (``{"name", "created_at", "model", "message_count"}``) sorted
            newest-first.  When provided, the top 3 are shown so the user can
            quickly ``/load`` back into a previous conversation.
    """
    print_logo(model=model)

    # ── Command groups (categorised for scannability) ────────────────
    # Each tuple: (group label, [(command, description), ...])
    command_groups = [
        ("General", [
            ("/help",       "Show this help message"),
            ("/clear",      "Clear conversation history"),
            ("/exit",       "Exit the CLI"),
            ("/cost",       "Show token usage and cost"),
            ("/approval",   "Show or set approval mode"),
        ]),
        ("Files & Code", [
            ("/add <file>",  "Add file to conversation context"),
            ("/drop <file>", "Remove file from context"),
            ("/ls",          "List context files"),
            ("/lint",        "Run linter  ('on'/'off' to toggle)"),
            ("/test",        "Run tests    ('on'/'off' to toggle)"),
        ]),
        ("Git", [
            ("/diff",         "Show uncommitted changes"),
            ("/commit [msg]", "Commit (AI writes message if none)"),
            ("/undo",         "Undo last AI commit"),
        ]),
        ("Session & Context", [
            ("/save [name]",   "Save current session"),
            ("/load <name>",   "Load a saved session"),
            ("/history",       "List saved sessions"),
            ("/web <url>",     "Fetch web page into context"),
            ("/model <name>",  "Switch AI model (deepseek/anthropic/openai)"),
            ("/architect",     "Enter architect mode (plan first)"),
            ("/code",          "Return to normal coding mode"),
            ("/think",         "View last AI reasoning content"),
            ("/compact",       "Summarize conversation to free context"),
            ("/export",        "Export conversation as Markdown"),
            ("/tree",          "Visualize session tree"),
            ("/branch",        "Branch from a specific message"),
        ]),
    ]

    # Render each group as a compact borderless Table prefixed by a dim header.
    cmd_col_width = _adaptive_limit(default=22, narrow=14)
    for group_label, items in command_groups:
        console.print(f"[role.tool] {group_label} [/role.tool]")
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Command", style="role.user", no_wrap=True, width=cmd_col_width)
        table.add_column("Description", style="dim", overflow="ellipsis", no_wrap=False)
        for cmd, desc in items:
            table.add_row(cmd, desc)
        console.print(table)
        console.print()

    # ── Recent sessions (quick /load shortcuts) ──────────────────────
    if recent_sessions:
        shown = recent_sessions[:3]
        if shown:
            console.print("[role.tool] Recent Sessions [/role.tool]")
            sess_table = Table(show_header=False, box=None, padding=(0, 2))
            sess_table.add_column("Name", style="accent.model", no_wrap=True, width=_adaptive_limit(default=22, narrow=18))
            sess_table.add_column("Model", style="dim", width=18, no_wrap=True)
            sess_table.add_column("Msgs", style="dim", justify="right", width=6)
            sess_table.add_column("Created", style="dim", width=17, no_wrap=True)
            for s in shown:
                created = str(s.get("created_at", ""))[:16]
                sess_table.add_row(
                    str(s.get("name", "?")),
                    str(s.get("model", "?")),
                    str(s.get("message_count", 0)),
                    created,
                )
            # On narrow terminals drop the Model/Created columns to save width.
            if _is_narrow():
                sess_table = Table(show_header=False, box=None, padding=(0, 2))
                sess_table.add_column("Name", style="accent.model", no_wrap=True, width=18)
                sess_table.add_column("Msgs", style="dim", justify="right", width=6)
                for s in shown:
                    sess_table.add_row(
                        str(s.get("name", "?")),
                        str(s.get("message_count", 0)),
                    )
            console.print(sess_table)
            console.print(
                "[dim]Use [bold]/load <name>[/bold] to resume a session.[/dim]"
            )
            console.print()

    console.print("[dim]Type your message and press Enter to interact.[/dim]")
    console.print()
