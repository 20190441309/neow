"""Effort level picker screen."""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from rich.text import Text
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from neow.tui.theme import get_palette

EFFORT_OPTIONS: List[Tuple[str, str, str]] = [
    ("off", "关闭思考", "不启用额外推理，响应最快"),
    ("low", "轻度思考", "快速响应，简短推理"),
    ("medium", "中度思考", "平衡推理深度与耗时，适合常规任务"),
    ("high", "深度思考", "最大推理强度，适合复杂任务与算法推导"),
]


class EffortPickerScreen(ModalScreen):
    """Pick an effort level (off, low, medium, high); Enter selects and dismisses."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    EffortPickerScreen .dialog {
        width: 72;
    }
    EffortPickerScreen OptionList {
        height: auto;
        max-height: 10;
    }
    """

    def __init__(
        self,
        *,
        current: str = "off",
        model_name: Optional[str] = None,
        on_select: Callable[[str], None],
    ):
        super().__init__()
        self.current = (current or "off").lower()
        self.model_name = model_name or "当前模型"
        self.on_select = on_select
        self.levels = [item[0] for item in EFFORT_OPTIONS]

    def _render_option(self, code: str, title: str, desc: str, palette: dict) -> Text:
        active = code == self.current
        out = Text(no_wrap=True, overflow="ellipsis")
        icon = "● " if active else "○ "
        out.append(icon, palette["accent1"] if active else palette["muted"])
        out.append(
            f"{code:<8}",
            f"bold {palette['text']}" if active else palette["text"],
        )
        out.append(f"  {title:<8}", palette["accent2"] if active else palette["dim"])
        out.append(f"   {desc}", palette["muted"])
        if active:
            out.append("  当前", palette["success"])
        return out

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = f"◆ 思考强度 · {self.model_name}"
        box.border_subtitle = "↑↓ 选择 · enter 确认 · esc 返回"
        with box:
            palette = get_palette(self.app)
            yield OptionList(
                *[
                    Option(self._render_option(code, title, desc, palette))
                    for code, title, desc in EFFORT_OPTIONS
                ],
                id="effort-list",
            )

    def on_mount(self) -> None:
        options = self.query_one(OptionList)
        options.focus()
        if self.current in self.levels:
            options.highlighted = self.levels.index(self.current)
        else:
            options.highlighted = 0

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        level = self.levels[event.option_index]
        self.on_select(level)
        self.app.pop_screen()


__all__ = ["EffortPickerScreen"]
