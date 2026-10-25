"""Architect / Code mode picker screen."""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from rich.text import Text
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from neow.tui.theme import get_palette

MODE_OPTIONS: List[Tuple[str, str, str]] = [
    ("code", "标准编码模式", "由当前配置的模型独立完成思考、代码读写与执行全流程"),
    (
        "architect",
        "架构师双模型模式",
        "由规划模型 (Planner) 先行设计方案，再由执行模型 (Executor) 落地改动",
    ),
]


class ModePickerScreen(ModalScreen):
    """Pick an operating mode (code / architect); Enter selects and dismisses."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    ModePickerScreen .dialog {
        width: 78;
    }
    ModePickerScreen OptionList {
        height: auto;
        max-height: 8;
    }
    ModePickerScreen #mode-details {
        margin-top: 1;
        height: auto;
    }
    """

    def __init__(
        self,
        *,
        current: str = "code",
        planner_model: Optional[str] = None,
        executor_model: Optional[str] = None,
        on_select: Callable[[str], None],
    ):
        super().__init__()
        self.current = (current or "code").lower()
        self.planner_model = planner_model or "anthropic"
        self.executor_model = executor_model or "deepseek"
        self.on_select = on_select
        self.modes = [item[0] for item in MODE_OPTIONS]

    def _render_option(self, code: str, title: str, desc: str, palette: dict) -> Text:
        active = code == self.current
        out = Text(no_wrap=True, overflow="ellipsis")
        icon = "● " if active else "○ "
        out.append(icon, palette["accent1"] if active else palette["muted"])
        out.append(
            f"{code:<12}",
            f"bold {palette['text']}" if active else palette["text"],
        )
        out.append(f"  {title:<12}", palette["accent2"] if active else palette["dim"])
        out.append(f"   {desc}", palette["muted"])
        if active:
            out.append("  当前", palette["success"])
        return out

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 工作模式"
        box.border_subtitle = "↑↓ 选择 · enter 确认 · esc 返回"
        with box:
            palette = get_palette(self.app)
            yield OptionList(
                *[
                    Option(self._render_option(code, title, desc, palette))
                    for code, title, desc in MODE_OPTIONS
                ],
                id="mode-list",
            )
            detail = Text("◇ 架构师分工  ", style=palette["muted"])
            detail.append(f"Planner={self.planner_model}", style=palette["info"])
            detail.append("  ·  ", style=palette["muted"])
            detail.append(f"Executor={self.executor_model}", style=palette["accent3"])
            yield Static(detail, id="mode-details")

    def on_mount(self) -> None:
        options = self.query_one(OptionList)
        options.focus()
        if self.current in self.modes:
            options.highlighted = self.modes.index(self.current)
        else:
            options.highlighted = 0

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        mode = self.modes[event.option_index]
        self.on_select(mode)
        self.app.pop_screen()


__all__ = ["ModePickerScreen"]
