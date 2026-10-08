"""Cost breakdown screen."""

from __future__ import annotations

from rich.text import Text
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static


class CostScreen(ModalScreen):
    """Token usage and session cost summary."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]

    def __init__(self, *, summary: str):
        super().__init__()
        self.summary = summary or "(no usage recorded)"

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "用量与费用"
        box.border_subtitle = "esc 返回"
        with box:
            with VerticalScroll():
                yield Static(Text(self.summary), id="cost-body")

    def on_mount(self) -> None:
        self.query_one(VerticalScroll).focus()


__all__ = ["CostScreen"]
