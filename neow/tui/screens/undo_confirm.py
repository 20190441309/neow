"""Undo last AI commit confirmation dialog for /undo."""

from __future__ import annotations

from typing import Callable

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class UndoConfirmScreen(ModalScreen):
    """Confirm undoing last commit."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    UndoConfirmScreen .dialog {
        width: 66;
    }
    UndoConfirmScreen .dialog-msg {
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
        box.border_title = "◆ 撤销上次提交"
        box.border_subtitle = "esc 返回"
        with box:
            yield Static(
                "确定要撤销上一次由 AI 创建的 Git Commit 吗？\n该操作会重置该次提交，但会保留工作区修改文件。",
                classes="dialog-msg",
            )
            with Horizontal(classes="actions"):
                yield Button("确认撤销", variant="warning", id="confirm-btn")
                yield Button("取消", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#cancel-btn", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self.on_confirm()
            self.app.pop_screen()
        else:
            self.app.pop_screen()


__all__ = ["UndoConfirmScreen"]
