"""Lint runner and report dialog for /lint."""

from __future__ import annotations

from typing import Callable, Optional

from rich.text import Text
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from neow.tui.theme import get_palette


class LintModalScreen(ModalScreen):
    """Run lint and display results in modal."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [
        ("escape", "app.pop_screen", "返回"),
        ("q", "app.pop_screen", "返回"),
    ]
    DEFAULT_CSS = """
    LintModalScreen .dialog {
        width: 82;
        height: auto;
        max-height: 82%;
    }
    LintModalScreen #lint-scroll {
        height: auto;
        max-height: 16;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        *,
        command: str = "",
        output: str = "",
        on_auto_fix: Optional[Callable[[], None]] = None,
    ):
        super().__init__()
        self.cmd = command
        self.output = output.strip()
        self.on_auto_fix = on_auto_fix

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 代码规范检查"
        box.border_subtitle = "q / esc 关闭"
        palette = get_palette(self.app)
        with box:
            header = Text()
            header.append("◇ 命令  ", style=palette["muted"])
            header.append(
                self.cmd or "自动探测 (flake8 / eslint…)", style=palette["dim"]
            )
            yield Static(header, classes="dialog-label")
            with VerticalScroll(id="lint-scroll", classes="dialog-block"):
                yield Static(
                    self.output or "● 未发现代码规范问题，检查通过", markup=False
                )
            if self.on_auto_fix and self.output:
                with Horizontal(classes="actions"):
                    yield Button("让 AI 修复", variant="primary", id="fix-btn")
                    yield Button("关闭", id="close-btn")

    def on_mount(self) -> None:
        self.query_one("#lint-scroll", VerticalScroll).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "fix-btn" and self.on_auto_fix:
            self.app.pop_screen()
            self.on_auto_fix()
        else:
            self.app.pop_screen()


__all__ = ["LintModalScreen"]
