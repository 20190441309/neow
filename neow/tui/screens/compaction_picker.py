"""Context compaction strategy picker screen for /compact."""

from __future__ import annotations

from typing import Callable, List, Tuple

from rich.text import Text
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from neow.tui.theme import get_palette

COMPACTION_OPTIONS: List[Tuple[str, str, str]] = [
    ("full", "全量深度压缩", "提炼总结全部历史对话，彻底释放上下文空间"),
    ("recent", "增量压缩 (保留近期)", "保留最近 5 轮完整上下文，仅压缩更早的会话历史"),
    (
        "handoff",
        "任务交接压缩 (Handoff)",
        "生成结构化任务与代码状态交接备忘并压缩早期上下文",
    ),
]


class CompactionPickerScreen(ModalScreen):
    """Pick compaction strategy; Enter selects and dismisses."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    CompactionPickerScreen .dialog {
        width: 78;
    }
    CompactionPickerScreen OptionList {
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
        self.strategies = [item[0] for item in COMPACTION_OPTIONS]

    def _render_option(self, code: str, title: str, desc: str, palette: dict) -> Text:
        out = Text(no_wrap=True, overflow="ellipsis")
        out.append("▸ ", palette["accent1"])
        out.append(f"{code:<10}", f"bold {palette['text']}")
        out.append(f"  {title:<16}", palette["accent2"])
        out.append(f"   {desc}", palette["muted"])
        return out

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 压缩上下文"
        box.border_subtitle = "↑↓ 选择 · enter 执行 · esc 返回"
        with box:
            palette = get_palette(self.app)
            yield OptionList(
                *[
                    Option(self._render_option(code, title, desc, palette))
                    for code, title, desc in COMPACTION_OPTIONS
                ],
                id="compaction-list",
            )

    def on_mount(self) -> None:
        options = self.query_one(OptionList)
        options.focus()
        options.highlighted = 0

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        strategy = self.strategies[event.option_index]
        self.on_select(strategy)
        self.app.pop_screen()


__all__ = ["CompactionPickerScreen"]
