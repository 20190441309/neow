"""Exit confirmation dialog for /exit."""

from __future__ import annotations

from typing import Callable

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ExitConfirmScreen(ModalScreen):
    """Confirm exiting Neow TUI."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    ExitConfirmScreen .dialog {
        width: 66;
    }
    ExitConfirmScreen .dialog-msg {
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        *,
        on_exit: Callable[[bool], None],
    ):
        super().__init__()
        self.on_exit = on_exit

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 退出 Neow"
        box.border_subtitle = "esc 返回"
        with box:
            yield Static(
                "确定要退出 Neow 吗？\n你可以选择保存当前会话进度，下次可通过 /history 继续。",
                classes="dialog-msg",
            )
            with Horizontal(classes="actions"):
                yield Button("保存并退出", variant="primary", id="save-exit-btn")
                yield Button("直接退出", variant="error", id="direct-exit-btn")
                yield Button("取消", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#cancel-btn", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-exit-btn":
            self.app.pop_screen()
            self.on_exit(True)
        elif event.button.id == "direct-exit-btn":
            self.app.pop_screen()
            self.on_exit(False)
        else:
            self.app.pop_screen()


__all__ = ["ExitConfirmScreen"]
