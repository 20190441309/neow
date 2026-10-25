"""Image diff input modal for /imgdiff."""

from __future__ import annotations

from typing import Callable

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class ImgDiffModalScreen(ModalScreen):
    """Input two image paths to compute pixel visual diff."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    ImgDiffModalScreen .dialog {
        width: 72;
    }
    ImgDiffModalScreen #img1-input {
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        *,
        on_compare: Callable[[str, str], None],
    ):
        super().__init__()
        self.on_compare = on_compare

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 图片差异对比"
        box.border_subtitle = "enter 下一步/提交 · esc 返回"
        with box:
            yield Static("◇ 基准图片 (Baseline)", classes="dialog-label")
            yield Input(placeholder="输入基准图片路径，如 before.png…", id="img1-input")
            yield Static("◇ 对比图片 (Target)", classes="dialog-label")
            yield Input(placeholder="输入对比图片路径，如 after.png…", id="img2-input")
            with Horizontal(classes="actions"):
                yield Button("开始对比", variant="primary", id="compare-btn")
                yield Button("取消", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#img1-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.app.pop_screen()
        elif event.button.id == "compare-btn":
            self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "img1-input":
            self.query_one("#img2-input", Input).focus()
        else:
            self._submit()

    def _submit(self) -> None:
        img1 = self.query_one("#img1-input", Input).value.strip()
        img2 = self.query_one("#img2-input", Input).value.strip()
        if img1 and img2:
            self.on_compare(img1, img2)
            self.app.pop_screen()


__all__ = ["ImgDiffModalScreen"]
