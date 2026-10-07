"""System info/warn and error cards."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from neow.tui.theme import MIDNIGHT
from neow.tui.widgets.cards.base import CardBase

_SYSTEM_LEVELS = {
    "info": ("ℹ", "info"),
    "warn": ("⚠", "warn"),
    "error": ("✗", "error"),
}


class SystemCard(CardBase):
    """Info/warn message; short messages live in the title row."""

    def __init__(self, message: str, *, level: str = "info"):
        icon, key = _SYSTEM_LEVELS.get(level, _SYSTEM_LEVELS["info"])
        short = len(message) <= 80 and "\n" not in message
        super().__init__(
            title=message if short else "System",
            icon=icon,
            accent=MIDNIGHT[key],
        )
        self.accent_key = key
        self.message = message
        self.level = level
        if not short:
            self.add_body(Static(Text(message)), message)


class ErrorCard(CardBase):
    """Error with a title and optional detail body."""

    accent_key = "error"

    def __init__(self, title: str, detail: str = ""):
        super().__init__(title=title, icon="✗", accent=MIDNIGHT["error"])
        self.detail = detail
        if detail:
            self.add_body(Static(Text(detail)), detail)


__all__ = ["SystemCard", "ErrorCard"]
