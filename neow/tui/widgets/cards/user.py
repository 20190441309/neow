"""User prompt card."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from neow.tui.widgets.cards.base import CardBase


class UserCard(CardBase):
    """User prompt: cyan accent, multiline text preserved."""

    accent_key = "role_user"

    def __init__(self, text: str, *, number: int, timestamp: str):
        super().__init__(
            title=f"You #{number}",
            icon="❯",
            meta=f"· {timestamp}",
            accent="#22d3ee",
        )
        self.text = text
        self.add_body(Static(Text(text)), text)


__all__ = ["UserCard"]
