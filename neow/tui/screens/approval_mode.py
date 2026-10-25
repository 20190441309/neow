"""Approval mode picker screen."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from rich.text import Text
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from neow.tui.theme import get_palette

APPROVAL_OPTIONS: List[Tuple[str, str, str]] = [
    ("always-ask", "严格审批", "所有工具调用（文件修改、命令等）均需人工确认"),
    ("write", "写操作审批", "修改/创建/删除与外部命令需确认，只读工具自动允许"),
    ("yolo", "极速自主 (YOLO)", "所有工具均免确认自动运行，适合受信测试环境"),
]


class ApprovalModeScreen(ModalScreen):
    """Pick an approval mode; Enter selects and dismisses."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    ApprovalModeScreen .dialog {
        width: 76;
    }
    ApprovalModeScreen OptionList {
        height: auto;
        max-height: 8;
    }
    ApprovalModeScreen #approval-overrides {
        margin-top: 1;
        height: auto;
    }
    """

    def __init__(
        self,
        *,
        current: str = "write",
        overrides: Optional[Dict[str, str]] = None,
        on_select: Callable[[str], None],
    ):
        super().__init__()
        self.current = (current or "write").lower()
        self.overrides = dict(overrides or {})
        self.on_select = on_select
        self.modes = [item[0] for item in APPROVAL_OPTIONS]

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
        box.border_title = "◆ 审批模式"
        box.border_subtitle = "↑↓ 选择 · enter 确认 · esc 返回"
        with box:
            palette = get_palette(self.app)
            yield OptionList(
                *[
                    Option(self._render_option(code, title, desc, palette))
                    for code, title, desc in APPROVAL_OPTIONS
                ],
                id="approval-list",
            )
            if self.overrides:
                override_text = Text("◇ 单工具覆盖  ", style=palette["muted"])
                override_text.append(
                    ", ".join(f"{k} -> {v}" for k, v in self.overrides.items()),
                    style=palette["info"],
                )
                yield Static(override_text, id="approval-overrides")

    def on_mount(self) -> None:
        options = self.query_one(OptionList)
        options.focus()
        if self.current in self.modes:
            options.highlighted = self.modes.index(self.current)
        else:
            options.highlighted = 1

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        mode = self.modes[event.option_index]
        self.on_select(mode)
        self.app.pop_screen()


__all__ = ["ApprovalModeScreen"]
