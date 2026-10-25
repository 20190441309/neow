"""Clear conversation confirmation dialog for /clear."""

from __future__ import annotations

from typing import Callable

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ClearConfirmScreen(ModalScreen):
    """Confirm clearing conversation history."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    ClearConfirmScreen .dialog {
        width: 64;
    }
    ClearConfirmScreen .dialog-msg {
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        *,
        on_confirm: Callable[[], None],
    ):
        super().__init__()
        self.on_confirm = on_confirm

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 清空对话历史"
        box.border_subtitle = "esc 返回"
        with box:
            yield Static(
                "确定要清空当前的全部对话记录吗？\n该操作不可撤销，如有需要可先使用 /save 保存会话。",
                classes="dialog-msg",
            )
            with Horizontal(classes="actions"):
                yield Button("清空对话", variant="error", id="confirm-btn")
                yield Button("取消", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#cancel-btn", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self.on_confirm()
            self.app.pop_screen()
        else:
            self.app.pop_screen()


__all__ = ["ClearConfirmScreen"]
