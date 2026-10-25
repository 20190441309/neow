"""Thinking process display toggle and viewer screen for /thinking."""

from __future__ import annotations

from typing import Callable, List, Tuple

from rich.text import Text
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from neow.tui.theme import get_palette

THINKING_OPTIONS: List[Tuple[str, str, str]] = [
    ("on", "开启实时显示", "在时间轴中实时展示模型推理与折叠思考卡片"),
    ("off", "关闭实时显示", "静默接收模型思考，不插入思考卡片，界面清爽"),
    ("view", "查看思考详情", "全屏弹窗阅读上一轮 AI 响应的完整思维链"),
]


class ThinkingPickerScreen(ModalScreen):
    """Pick whether to show/hide thinking cards or view the last reasoning trace."""

    __test__ = False

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    ThinkingPickerScreen .dialog {
        width: 76;
    }
    ThinkingPickerScreen OptionList {
        height: auto;
        max-height: 8;
    }
    """

    def __init__(
        self,
        *,
        current: bool = True,
        on_select: Callable[[str], None],
    ):
        super().__init__()
        self.current_bool = current
        self.current = "on" if current else "off"
        self.on_select = on_select
        self.levels = [item[0] for item in THINKING_OPTIONS]

    def _render_option(self, code: str, title: str, desc: str, palette: dict) -> Text:
        active = code == self.current
        out = Text(no_wrap=True, overflow="ellipsis")
        if code == "view":
            out.append("◇ ", palette["accent2"])
        else:
            icon = "● " if active else "○ "
            out.append(icon, palette["accent1"] if active else palette["muted"])
        out.append(
            f"{code:<6}",
            f"bold {palette['text']}" if active else palette["text"],
        )
        out.append(f"  {title:<12}", palette["accent2"] if active else palette["dim"])
        out.append(f"   {desc}", palette["muted"])
        if active and code in ("on", "off"):
            out.append("  当前", palette["success"])
        return out

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 思考过程"
        box.border_subtitle = "↑↓ 选择 · enter 确认 · esc 返回"
        with box:
            palette = get_palette(self.app)
            yield OptionList(
                *[
                    Option(self._render_option(code, title, desc, palette))
                    for code, title, desc in THINKING_OPTIONS
                ],
                id="thinking-list",
            )

    def on_mount(self) -> None:
        options = self.query_one(OptionList)
        options.focus()
        options.highlighted = 0 if self.current_bool else 1

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        level = self.levels[event.option_index]
        self.app.pop_screen()
        self.on_select(level)


__all__ = ["ThinkingPickerScreen", "THINKING_OPTIONS"]
