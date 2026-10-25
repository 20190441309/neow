"""Web fetch URL input modal for /web."""

from __future__ import annotations

from typing import Callable

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input


class WebFetchScreen(ModalScreen):
    """Input a web URL to fetch and inject into context."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    WebFetchScreen .dialog {
        width: 72;
    }
    """

    def __init__(
        self,
        *,
        on_fetch: Callable[[str], None],
    ):
        super().__init__()
        self.on_fetch = on_fetch

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 抓取网页"
        box.border_subtitle = "enter 读取 · esc 返回"
        with box:
            yield Input(
                placeholder="https://docs.python.org/…",
                id="url-input",
            )
            with Horizontal(classes="actions"):
                yield Button("抓取网页", variant="primary", id="fetch-btn")
                yield Button("取消", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.app.pop_screen()
        elif event.button.id == "fetch-btn":
            self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        val = self.query_one(Input).value.strip()
        if val:
            self.on_fetch(val)
            self.app.pop_screen()


__all__ = ["WebFetchScreen"]
