"""Cost breakdown screen."""

from __future__ import annotations

from rich.text import Text
from textual.screen import Screen
from textual.containers import VerticalScroll
from textual.widgets import Static


class CostScreen(Screen):
    """Token usage and session cost summary."""

    BINDINGS = [("escape", "app.pop_screen", "返回")]

    def __init__(self, *, summary: str):
        super().__init__()
        self.summary = summary or "(no usage recorded)"

    def compose(self):
        yield Static("COST · Esc 返回", classes="picker-title")
        with VerticalScroll():
            yield Static(Text(self.summary), id="cost-body")

    def on_mount(self) -> None:
        self.query_one(VerticalScroll).focus()


__all__ = ["CostScreen"]
