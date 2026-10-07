"""Chat screen scaffold (cards and wiring land in later plan tasks)."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from neow.tui.widgets.status_bar import StatusBar, TopBar


class ChatScreen(Screen):
    """Main screen: top bar, timeline, sidebar, input dock, status bar."""

    BINDINGS = [("ctrl+q", "quit_app", "Quit")]

    def compose(self):
        yield TopBar(id="topbar")
        with Horizontal(id="body"):
            yield VerticalScroll(id="timeline")
            yield Vertical(id="sidebar")
        yield Static(id="queuestrip")
        with Vertical(id="inputdock"):
            yield Static("❯ 输入消息…", id="input-placeholder")
        yield StatusBar(id="statusbar")

    def on_mount(self) -> None:
        self.apply_width_classes(self.size.width)

    def on_resize(self, event) -> None:
        self.apply_width_classes(event.size.width)

    def apply_width_classes(self, width: int) -> None:
        """Apply the spec §4.3 breakpoints (Textual CSS has no media queries)."""

        self.set_class(width < 110, "small-sidebar")
        self.set_class(width < 88, "no-sidebar")
        self.set_class(width < 72, "narrow")

    def action_quit_app(self) -> None:
        self.app.exit()
