"""Session save name input modal for /save."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input


class SessionSaveScreen(ModalScreen):
    """Input session name to save conversation."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    SessionSaveScreen .dialog {
        width: 70;
    }
    """

    def __init__(
        self,
        *,
        default_name: str = "",
        on_save: Callable[[str], None],
    ):
        super().__init__()
        self.default_name = default_name or datetime.now().strftime(
            "session-%Y%m%d-%H%M"
        )
        self.on_save = on_save

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 保存会话"
        box.border_subtitle = "enter 保存 · esc 返回"
        with box:
            yield Input(
                value=self.default_name,
                placeholder="输入会话标识名称…",
                id="session-name-input",
            )
            with Horizontal(classes="actions"):
                yield Button("保存会话", variant="primary", id="save-btn")
                yield Button("取消", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.app.pop_screen()
        elif event.button.id == "save-btn":
            self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        name = self.query_one(Input).value.strip() or self.default_name
        self.on_save(name)
        self.app.pop_screen()


__all__ = ["SessionSaveScreen"]
