"""System info/warn and error cards."""

from __future__ import annotations

from textual.widgets import Static

from neow.tui.widgets.cards.base import CardBase

_SYSTEM_LEVELS = {
    "info": ("ℹ", "#38bdf8"),
    "warn": ("⚠", "#facc15"),
    "error": ("✗", "#f87171"),
}


class SystemCard(CardBase):
    """Info/warn message; short messages live in the title row."""

    def __init__(self, message: str, *, level: str = "info"):
        icon, accent = _SYSTEM_LEVELS.get(level, _SYSTEM_LEVELS["info"])
        short = len(message) <= 80 and "\n" not in message
        super().__init__(
            title=message if short else "System",
            icon=icon,
            accent=accent,
        )
        self.message = message
        self.level = level
        if not short:
            self.add_body(Static(message), message)


class ErrorCard(CardBase):
    """Error with a title and optional detail body."""

    def __init__(self, title: str, detail: str = ""):
        super().__init__(title=title, icon="✗", accent="#f87171")
        self.detail = detail
        if detail:
            self.add_body(Static(detail), detail)


__all__ = ["SystemCard", "ErrorCard"]
