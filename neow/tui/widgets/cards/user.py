"""User prompt card."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from neow.tui.widgets.cards.base import CardBase


class UserCard(CardBase):
    """User prompt: tinted block with a cyan rule, multiline text preserved."""

    accent_key = "role_user"
    title_key = "role_user"
    rule = "outer"

    def __init__(self, text: str, *, number: int, timestamp: str):
        super().__init__(
            title="You",
            icon="❯",
            meta=f"#{number} · {timestamp}",
            accent="#22d3ee",
        )
        self.text = text
        self.add_body(Static(Text(text)), text)

    def mark_rewound(self) -> None:
        super().mark_rewound()
        self.set_title(subtitle="已回退")


__all__ = ["UserCard"]
