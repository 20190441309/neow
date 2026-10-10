"""Base timeline card: title row, collapsible body, accent rule."""

from __future__ import annotations

from typing import List, Optional

from rich.table import Table
from rich.text import Text
from textual.containers import Vertical
from textual.widgets import Static

from neow.tui.theme import widget_palette

DEFAULT_ACCENT = "#334155"


class CardBase(Vertical, can_focus=True):
    """A collapsible timeline card.

    The title row is a two-column grid: ``icon title subtitle`` on the left
    (truncated with an ellipsis) and ``meta`` right-aligned.  The icon carries
    the accent colour; cards opt into a visible left rule via ``rule``.
    """

    DEFAULT_CSS = """
    CardBase {
        background: transparent;
        padding: 0 1;
        margin: 1 0 0 0;
        height: auto;
    }
    CardBase .card-title {
        height: 1;
    }
    CardBase .card-body {
        height: auto;
        padding: 0 0 0 2;
    }
    """

    #: Palette key used by :meth:`apply_palette` for the accent rule.
    accent_key = None
    #: Left border kind; ``blank`` keeps alignment without drawing a bar.
    rule = "blank"
    #: Palette key for the title text (``None`` = regular text colour).
    title_key: Optional[str] = None
    #: Whether the title text is bold (low-emphasis cards turn this off).
    title_bold = True

    def __init__(
        self,
        *,
        title: str,
        icon: str = "",
        meta: str = "",
        accent: str = DEFAULT_ACCENT,
        card_id: Optional[str] = None,
        subtitle: str = "",
    ):
        super().__init__()
        self.card_id = card_id or f"card-{id(self):x}"
        self._title = title
        self._icon = icon
        self._meta = meta
        self._subtitle = subtitle
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
        self.styles.border_left = (self.rule, self.accent)
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

    def _render_title(self) -> Table:
        palette = widget_palette(self)
        left = Text(no_wrap=True, overflow="ellipsis")
        if self._icon:
            left.append(f"{self._icon} ", style=f"bold {self.accent}")
        title_color = palette[self.title_key] if self.title_key else palette["text"]
        weight = "bold " if self.title_bold else ""
        left.append(self._title, style=f"{weight}{title_color}")
        if self._subtitle:
            left.append(f"  {self._subtitle}", style=palette["dim"])
        grid = Table.grid(expand=True, padding=(0, 0, 0, 2))
        grid.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
        grid.add_column(justify="right", no_wrap=True)
        grid.add_row(left, Text(self._meta, style=palette["muted"]))
        return grid

    def title_text(self) -> str:
        head = f"{self._icon} {self._title}" if self._icon else self._title
        if self._subtitle:
            head = f"{head}  {self._subtitle}"
        parts = [head]
        if self._meta:
            parts.append(self._meta)
        return "   ".join(parts)

    def set_title(
        self,
        *,
        title: Optional[str] = None,
        icon: Optional[str] = None,
        meta: Optional[str] = None,
        subtitle: Optional[str] = None,
    ) -> None:
        if title is not None:
            self._title = title
        if icon is not None:
            self._icon = icon
        if meta is not None:
            self._meta = meta
        if subtitle is not None:
            self._subtitle = subtitle
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

    def on_click(self, event) -> None:
        if event.widget is self._title_widget:
            self.focus()
            self.toggle()

    def play_entrance(self) -> None:
        """Fade the card in (design spec §6.1; full effects mode only)."""

        self.styles.opacity = 0.0
        self.styles.animate("opacity", 1.0, duration=0.12, easing="out_cubic")

    # -- accent --------------------------------------------------------

    def set_accent(self, color: str) -> None:
        self.accent = color
        self.styles.border_left = (self.rule, color)
        if self.is_mounted:
            self._title_widget.update(self._render_title())

    def apply_palette(self, palette) -> None:
        """Adopt role colours from the active palette."""

        if self.accent_key and palette.get(self.accent_key):
            self.set_accent(palette[self.accent_key])

    # -- rewind --------------------------------------------------------

    rewound = False

    def mark_rewound(self) -> None:
        """Dim the card: its turn was removed from the conversation."""
        self.rewound = True
        self.add_class("rewound")
        self.styles.opacity = 0.45  # inline: overrides the entrance animation

    # -- text ----------------------------------------------------------

    def body_text(self) -> str:
        return "\n".join(self._body_texts)


__all__ = ["CardBase", "DEFAULT_ACCENT"]
