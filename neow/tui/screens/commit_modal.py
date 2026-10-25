"""Git commit interactive dialog for /commit."""

from __future__ import annotations

from typing import Callable, Optional

from rich.text import Text
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from neow.tui.theme import get_palette


class CommitModalScreen(ModalScreen):
    """Interactive commit dialog with message input and AI generate button."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    CommitModalScreen .dialog {
        width: 74;
    }
    CommitModalScreen #commit-summary {
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        *,
        changed_files_summary: str = "",
        on_commit: Callable[[str], None],
        on_generate_ai: Optional[Callable[[], None]] = None,
    ):
        super().__init__()
        self.summary = changed_files_summary
        self.on_commit = on_commit
        self.on_generate_ai = on_generate_ai

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 提交改动"
        box.border_subtitle = "enter 提交 · esc 返回"
        palette = get_palette(self.app)
        with box:
            if self.summary:
                info = Text("◇ 变更概览  ", style=palette["muted"])
                info.append(self.summary, style=palette["dim"])
                yield Static(info, id="commit-summary")
            yield Input(
                placeholder="输入提交信息 (例如 feat: 新增功能)…",
                id="commit-msg-input",
            )
            with Horizontal(classes="actions"):
                yield Button("提交改动", variant="primary", id="commit-btn")
                if self.on_generate_ai:
                    yield Button("AI 生成说明", id="ai-btn")
                yield Button("取消", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.app.pop_screen()
        elif event.button.id == "commit-btn":
            self._do_commit()
        elif event.button.id == "ai-btn":
            self.app.pop_screen()
            if self.on_generate_ai:
                self.on_generate_ai()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._do_commit()

    def _do_commit(self) -> None:
        msg = self.query_one(Input).value.strip()
        if msg:
            self.on_commit(msg)
            self.app.pop_screen()


__all__ = ["CommitModalScreen"]
