"""CLI entry-mode selection.

Pure logic so it can be unit-tested without a terminal.  The precedence
mirrors the design spec (§10):

1. ``--plain`` and ``--tui`` are mutually exclusive.
2. A one-shot prompt always wins (non-interactive).
3. ``--tui`` requires a TTY.
4. ``--plain`` always selects the classic REPL.
5. A TTY stdin+stdout defaults to the TUI.
6. Anything else falls back to the classic REPL.
"""

from enum import Enum
from typing import Optional


class RunMode(str, Enum):
    """How the CLI should present itself."""

    TUI = "tui"
    PLAIN = "plain"
    ONESHOT = "oneshot"


class ModeError(Exception):
    """Raised when the requested entry mode cannot be honoured."""


def select_run_mode(
    *,
    prompt: Optional[str],
    plain: bool,
    tui: bool,
    stdin_tty: bool,
    stdout_tty: bool,
) -> RunMode:
    """Select the entry mode from CLI flags and terminal capabilities.

    Args:
        prompt: One-shot prompt, if any.
        plain: ``--plain`` flag.
        tui: ``--tui`` flag.
        stdin_tty: Whether stdin is a TTY.
        stdout_tty: Whether stdout is a TTY.

    Returns:
        The selected :class:`RunMode`.

    Raises:
        ModeError: If flags conflict or ``--tui`` is unusable.
    """
    if plain and tui:
        raise ModeError("--plain and --tui are mutually exclusive")
    if prompt:
        return RunMode.ONESHOT
    if tui:
        if not stdout_tty:
            raise ModeError("--tui requires a TTY")
        return RunMode.TUI
    if plain:
        return RunMode.PLAIN
    if stdout_tty and stdin_tty:
        return RunMode.TUI
    return RunMode.PLAIN
