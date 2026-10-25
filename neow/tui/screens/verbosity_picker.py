"""Verbosity level picker screen."""

from __future__ import annotations

from typing import Callable, List, Tuple

from rich.text import Text
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from neow.tui.theme import get_palette

VERBOSITY_OPTIONS: List[Tuple[str, str, str]] = [
    ("off", "标准模式", "仅展示工具名称与执行摘要，保持时间轴整洁清晰"),
    ("on", "详细模式 (Verbose)", "展开输出工具完整输入参数、执行细节与原始标准输出"),
]


class VerbosityPickerScreen(ModalScreen):
    """Pick tool verbosity level; Enter selects and dismisses."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    VerbosityPickerScreen .dialog {
        width: 72;
    }
    VerbosityPickerScreen OptionList {
        height: auto;
        max-height: 6;
    }
    """

    def __init__(
        self,
        *,
        current: bool = False,
        on_select: Callable[[bool], None],
    ):
        super().__init__()
        self.current_bool = current
        self.current = "on" if current else "off"
        self.on_select = on_select
        self.levels = [item[0] for item in VERBOSITY_OPTIONS]

    def _render_option(self, code: str, title: str, desc: str, palette: dict) -> Text:
        active = code == self.current
        out = Text(no_wrap=True, overflow="ellipsis")
        icon = "● " if active else "○ "
        out.append(icon, palette["accent1"] if active else palette["muted"])
        out.append(
            f"{code:<8}",
            f"bold {palette['text']}" if active else palette["text"],
        )
        out.append(f"  {title:<12}", palette["accent2"] if active else palette["dim"])
        out.append(f"   {desc}", palette["muted"])
        if active:
            out.append("  (当前)", palette["success"])
        return out

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "工具调用详细度 (Verbose)"
        box.border_subtitle = "↑↓ 选择 · enter 确定 · esc 返回"
        with box:
            palette = get_palette(self.app)
            yield OptionList(
                *[
                    Option(self._render_option(code, title, desc, palette))
                    for code, title, desc in VERBOSITY_OPTIONS
                ],
                id="verbose-list",
            )

    def on_mount(self) -> None:
        options = self.query_one(OptionList)
        options.focus()
        options.highlighted = 1 if self.current_bool else 0

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        level = self.levels[event.option_index]
        is_verbose = level == "on"
        self.on_select(is_verbose)
        self.app.pop_screen()


__all__ = ["VerbosityPickerScreen"]
