"""Diff view screen (diff / commit / undo)."""

from __future__ import annotations

from typing import Callable, Optional

from rich.text import Text
from textual.screen import Screen
from textual.containers import VerticalScroll
from textual.widgets import Static


class DiffScreen(Screen):
    """Show a git diff; ``c`` commits, ``u`` undoes (callbacks provided)."""

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
        yield Static("DIFF · c 提交 · u 回退 · Esc 返回", classes="picker-title")
        with VerticalScroll():
            yield Static(
                Text(self.diff_text or "(no uncommitted changes)"), id="diff-body"
            )

    def on_mount(self) -> None:
        self.query_one(VerticalScroll).focus()

    def action_commit(self) -> None:
        self.committed = True
        if self.on_commit is not None:
            self.on_commit()

    def action_undo(self) -> None:
        self.undone = True
        if self.on_undo is not None:
            self.on_undo()


__all__ = ["DiffScreen"]
