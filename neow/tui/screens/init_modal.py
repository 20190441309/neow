"""Project initialization dialog for /init."""

from __future__ import annotations

from typing import Callable

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class InitModalScreen(ModalScreen):
    """Confirm and generate AGENTS.md for current workspace."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    InitModalScreen .dialog {
        width: 78;
        height: auto;
        max-height: 80%;
    }
    InitModalScreen #init-scroll {
        height: auto;
        max-height: 12;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        *,
        preview_text: str = "",
        on_generate: Callable[[], None],
    ):
        super().__init__()
        self.preview = preview_text.strip()
        self.on_generate = on_generate

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 初始化项目规则 (AGENTS.md)"
        box.border_subtitle = "esc 返回"
        with box:
            yield Static(
                "◇ 扫描当前仓库结构并生成推荐的项目 AI 规范说明：",
                classes="dialog-label",
            )
            with VerticalScroll(id="init-scroll", classes="dialog-block"):
                yield Static(
                    self.preview
                    or "生成包含技术栈、编码约定、构建与测试指令的 AGENTS.md",
                    markup=False,
                )
            with Horizontal(classes="actions"):
                yield Button("生成 AGENTS.md", variant="primary", id="gen-btn")
                yield Button("取消", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "gen-btn":
            self.on_generate()
            self.app.pop_screen()
        else:
            self.app.pop_screen()


__all__ = ["InitModalScreen"]
