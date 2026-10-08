"""Diff view screen (diff / commit / undo)."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from rich.text import Text
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from neow.tui.theme import get_palette


def colorize_diff(diff: str, palette: Dict[str, Any]) -> Text:
    """Unified diff with per-line colours (headers, hunks, +/- lines)."""

    out = Text()
    for line in diff.splitlines():
        if line.startswith(("diff --git", "index ")):
            style = f"bold {palette['text']}"
        elif line.startswith(("+++", "---")):
            style = palette["dim"]
        elif line.startswith("@@"):
            style = palette["accent1"]
        elif line.startswith("+"):
            style = palette["success"]
        elif line.startswith("-"):
            style = palette["error"]
        else:
            style = palette["muted"]
        out.append(line + "\n", style)
    out.rstrip()
    return out


class DiffScreen(ModalScreen):
    """Show a git diff; ``c`` commits, ``u`` undoes (callbacks provided)."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [
        ("escape", "app.pop_screen", "返回"),
        ("c", "commit", "提交"),
        ("u", "undo", "回退"),
    ]

    def __init__(
        self,
        *,
        diff_text: str,
        on_commit: Optional[Callable[[], None]] = None,
        on_undo: Optional[Callable[[], None]] = None,
    ):
        super().__init__()
        self.diff_text = diff_text or ""
        self.on_commit = on_commit
        self.on_undo = on_undo
        self.committed = False
        self.undone = False

    def compose(self):
        box = Vertical(classes="dialog tall wide")
        box.border_title = "改动"
        box.border_subtitle = "c 提交 · u 回退 · esc 返回"
        with box:
            with VerticalScroll():
                yield Static(id="diff-body")

    def on_mount(self) -> None:
        palette = get_palette(self.app)
        body = (
            colorize_diff(self.diff_text, palette)
            if self.diff_text
            else Text("没有未提交的改动", style=f"italic {palette['muted']}")
        )
        self.query_one("#diff-body", Static).update(body)
        self.query_one(VerticalScroll).focus()

    def action_commit(self) -> None:
        self.committed = True
        if self.on_commit is not None:
            self.on_commit()

    def action_undo(self) -> None:
        self.undone = True
        if self.on_undo is not None:
            self.on_undo()


__all__ = ["DiffScreen", "colorize_diff"]
