"""Base timeline card: title row, collapsible body, accent rule."""

from __future__ import annotations

from typing import List, Optional

from rich.text import Text
from textual.containers import Vertical
from textual.widgets import Static

DEFAULT_ACCENT = "#334155"


class CardBase(Vertical):
    """A collapsible timeline card."""

    DEFAULT_CSS = """
    CardBase {
        background: #0f1117;
        border-left: heavy #334155;
        padding: 0 2;
        margin: 0 0 1 0;
        height: auto;
    }
    CardBase .card-title {
        height: auto;
        text-style: bold;
    }
    CardBase .card-body {
        height: auto;
    }
    """

    def __init__(
        self,
        *,
        title: str,
        icon: str = "",
        meta: str = "",
        accent: str = DEFAULT_ACCENT,
        card_id: Optional[str] = None,
    ):
        super().__init__()
        self.card_id = card_id or f"card-{id(self):x}"
        self._title = title
        self._icon = icon
        self._meta = meta
        self.accent = accent
        self._collapsed = False
        self._body_widgets: List = []
        self._body_texts: List[str] = []
        self._title_widget = Static(self._render_title(), classes="card-title")
        self.body = Vertical(classes="card-body")

    # -- composition ---------------------------------------------------

    def compose(self):
        yield self._title_widget
        yield self.body

    def on_mount(self) -> None:
        self.styles.border_left = ("heavy", self.accent)
        self._title_widget.update(self._render_title())
        for widget in self._body_widgets:
            self.body.mount(widget)

    def add_body(self, widget, text: str = "") -> None:
        """Queue a body widget (and its plain text for assertions)."""

        self._body_widgets.append(widget)
        self._body_texts.append(text)
        if self.is_mounted:
            self.body.mount(widget)

    # -- title ---------------------------------------------------------

    def _render_title(self) -> Text:
        out = Text()
        if self._icon:
            out.append(f"{self._icon} ")
        out.append(self._title)
        if self._meta:
            out.append(f"   {self._meta}", style="#64748b")
        return out

    def title_text(self) -> str:
        parts = [f"{self._icon} {self._title}" if self._icon else self._title]
        if self._meta:
            parts.append(self._meta)
        return "   ".join(parts)

    def set_title(
        self,
        *,
        title: Optional[str] = None,
        icon: Optional[str] = None,
        meta: Optional[str] = None,
    ) -> None:
        if title is not None:
            self._title = title
        if icon is not None:
            self._icon = icon
        if meta is not None:
            self._meta = meta
        if self.is_mounted:
            self._title_widget.update(self._render_title())

    # -- collapse ------------------------------------------------------

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def _set_collapsed(self, value: bool) -> None:
        """Set collapse state without marking it as a user action."""

        self._collapsed = value
        self.body.display = not value
        self.set_class(value, "collapsed")

    def toggle(self) -> None:
        self._set_collapsed(not self._collapsed)

    def play_entrance(self) -> None:
        """Fade the card in (design spec §6.1; full effects mode only)."""

        self.styles.opacity = 0.0
        self.styles.animate("opacity", 1.0, duration=0.12, easing="out_cubic")

    # -- accent --------------------------------------------------------

    def set_accent(self, color: str) -> None:
        self.accent = color
        self.styles.border_left = ("heavy", color)

    # -- text ----------------------------------------------------------

    def body_text(self) -> str:
        return "\n".join(self._body_texts)


__all__ = ["CardBase", "DEFAULT_ACCENT"]
