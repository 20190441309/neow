"""Context files list and inspection screen for /ls."""

from __future__ import annotations

from typing import Callable, List, Optional

from rich.text import Text
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from neow.tui.theme import get_palette


class ContextListScreen(ModalScreen):
    """View active context files and their token footprint."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [
        ("escape", "app.pop_screen", "返回"),
        ("q", "app.pop_screen", "返回"),
    ]
    DEFAULT_CSS = """
    ContextListScreen .dialog {
        width: 76;
    }
    ContextListScreen OptionList {
        height: auto;
        max-height: 14;
    }
    """

    def __init__(
        self,
        *,
        files: List[str],
        on_drop: Optional[Callable[[str], None]] = None,
    ):
        super().__init__()
        self.files = list(files)
        self.on_drop = on_drop

    def _render_option(self, path: str, palette: dict) -> Text:
        out = Text(no_wrap=True, overflow="ellipsis")
        out.append("◇ ", palette["accent1"])
        out.append(path, f"bold {palette['text']}")
        out.append("   enter 移出", palette["muted"])
        return out

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = f"◆ 上下文文件 ({len(self.files)})"
        box.border_subtitle = (
            "↑↓ 选择 · enter 移出 · esc 返回" if self.files else "q / esc 关闭"
        )
        with box:
            if not self.files:
                yield Static(
                    "○ 当前未载入任何上下文文件  ·  可通过 /add 或 @文件 添加",
                    classes="dialog-empty",
                )
                return
            palette = get_palette(self.app)
            yield OptionList(
                *[Option(self._render_option(f, palette)) for f in self.files],
                id="context-list",
            )

    def on_mount(self) -> None:
        if self.files:
            options = self.query_one(OptionList)
            options.focus()
            options.highlighted = 0

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if not self.files or self.on_drop is None:
            return
        target = self.files[event.option_index]
        self.on_drop(target)
        self.app.pop_screen()


__all__ = ["ContextListScreen"]
