"""Export format picker screen for /export."""

from __future__ import annotations

from typing import Callable, List, Tuple

from rich.text import Text
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from neow.tui.theme import get_palette

EXPORT_OPTIONS: List[Tuple[str, str, str]] = [
    (
        "markdown",
        "Markdown 文档 (.md)",
        "导出为结构化 Markdown 文档，适合分享与笔记归档",
    ),
    ("json", "JSON 原始数据 (.json)", "导出完整会话消息、工具调用与思考记录原始结构"),
    ("html", "HTML 静态网页 (.html)", "导出为美观的静态富文本网页，可在浏览器直接查看"),
]


class ExportPickerScreen(ModalScreen):
    """Pick conversation export format; Enter selects and dismisses."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    ExportPickerScreen .dialog {
        width: 78;
    }
    ExportPickerScreen OptionList {
        height: auto;
        max-height: 8;
    }
    """

    def __init__(
        self,
        *,
        on_select: Callable[[str], None],
    ):
        super().__init__()
        self.on_select = on_select
        self.formats = [item[0] for item in EXPORT_OPTIONS]

    def _render_option(self, code: str, title: str, desc: str, palette: dict) -> Text:
        out = Text(no_wrap=True, overflow="ellipsis")
        out.append("◇ ", palette["accent1"])
        out.append(f"{code:<10}", f"bold {palette['text']}")
        out.append(f"  {title:<16}", palette["accent2"])
        out.append(f"   {desc}", palette["muted"])
        return out

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 导出会话"
        box.border_subtitle = "↑↓ 选择 · enter 导出 · esc 返回"
        with box:
            palette = get_palette(self.app)
            yield OptionList(
                *[
                    Option(self._render_option(code, title, desc, palette))
                    for code, title, desc in EXPORT_OPTIONS
                ],
                id="export-list",
            )

    def on_mount(self) -> None:
        options = self.query_one(OptionList)
        options.focus()
        options.highlighted = 0

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        fmt = self.formats[event.option_index]
        self.on_select(fmt)
        self.app.pop_screen()


__all__ = ["ExportPickerScreen"]
