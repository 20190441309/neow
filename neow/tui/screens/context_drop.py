"""Context file drop screen."""

from __future__ import annotations

from typing import Callable, List

from rich.text import Text
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from neow.tui.theme import get_palette


class ContextDropScreen(ModalScreen):
    """Pick a context file to drop; Enter removes it and dismisses."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [
        ("escape", "app.pop_screen", "返回"),
        ("q", "app.pop_screen", "返回"),
    ]
    DEFAULT_CSS = """
    ContextDropScreen .dialog {
        width: 76;
    }
    ContextDropScreen OptionList {
        height: auto;
        max-height: 12;
    }
    """

    def __init__(
        self,
        *,
        files: List[str],
        on_drop: Callable[[str], None],
    ):
        super().__init__()
        self.files = list(files)
        self.on_drop = on_drop

    def _render_option(self, path: str, palette: dict) -> Text:
        out = Text(no_wrap=True, overflow="ellipsis")
        out.append("✕ ", palette["error"])
        out.append(path, f"bold {palette['text']}")
        out.append("   enter 移出", palette["muted"])
        return out

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 移出上下文文件"
        box.border_subtitle = (
            "↑↓ 选择 · enter 移出 · esc 返回" if self.files else "q / esc 关闭"
        )
        with box:
            if not self.files:
                yield Static(
                    "○ 当前未添加任何上下文文件  ·  可通过 /add 或 @文件 载入",
                    classes="dialog-empty",
                )
                return
            palette = get_palette(self.app)
            options = [Option(self._render_option(f, palette)) for f in self.files]
            if len(self.files) > 1:
                all_opt = Text("◆ 全部移出 (Drop All)", style=palette["warn"])
                options.append(Option(all_opt))
            yield OptionList(*options, id="drop-list")

    def on_mount(self) -> None:
        if self.files:
            options = self.query_one(OptionList)
            options.focus()
            options.highlighted = 0

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if not self.files:
            return
        idx = event.option_index
        if idx < len(self.files):
            target = self.files[idx]
        else:
            target = "__ALL__"
        self.on_drop(target)
        self.app.pop_screen()


__all__ = ["ContextDropScreen"]
