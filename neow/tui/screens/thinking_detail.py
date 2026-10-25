"""Thinking reasoning trace full-screen viewer for /thinking view."""

from __future__ import annotations

from rich.text import Text
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from neow.tui.theme import get_palette


class ThinkingDetailScreen(ModalScreen):
    """Full modal viewer for last reasoning trace."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [
        ("escape", "app.pop_screen", "返回"),
        ("q", "app.pop_screen", "返回"),
    ]
    DEFAULT_CSS = """
    ThinkingDetailScreen .dialog {
        width: 84;
        height: auto;
        max-height: 85%;
    }
    ThinkingDetailScreen #think-meta {
        margin-bottom: 1;
    }
    ThinkingDetailScreen #think-scroll {
        height: auto;
        max-height: 22;
    }
    """

    def __init__(self, *, reasoning: str = ""):
        super().__init__()
        self.reasoning = reasoning.strip()

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 推理过程"
        box.border_subtitle = "↑↓ 滚动 · q / esc 关闭"
        palette = get_palette(self.app)
        with box:
            if not self.reasoning:
                empty = Text()
                empty.append("○ ", style=palette["muted"])
                empty.append("当前会话暂无思考过程", style=palette["dim"])
                empty.append(
                    "  ·  可通过 /effort 开启模型思考强度", style=palette["muted"]
                )
                yield Static(empty, classes="dialog-empty")
                return
            chars = len(self.reasoning)
            meta = Text()
            meta.append("◇ ", style=palette["accent2"])
            meta.append("最近一次推理内容", style=f"bold {palette['text']}")
            meta.append(f"  ·  {chars} 字", style=palette["muted"])
            yield Static(meta, id="think-meta")
            with VerticalScroll(id="think-scroll", classes="dialog-block"):
                yield Static(self.reasoning, markup=False)

    def on_mount(self) -> None:
        if self.reasoning:
            self.query_one("#think-scroll", VerticalScroll).focus()


__all__ = ["ThinkingDetailScreen"]
