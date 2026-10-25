"""Checkpoint rewind picker screen for /rewind."""

from __future__ import annotations

from typing import Callable, Dict, List

from rich.text import Text
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from neow.tui.theme import get_palette


class RewindPickerScreen(ModalScreen):
    """Pick a checkpoint to rewind files and chat state."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [
        ("escape", "app.pop_screen", "返回"),
        ("q", "app.pop_screen", "返回"),
    ]
    DEFAULT_CSS = """
    RewindPickerScreen .dialog {
        width: 78;
    }
    RewindPickerScreen OptionList {
        height: auto;
        max-height: 12;
    }
    """

    def __init__(
        self,
        *,
        checkpoints: List[Dict],
        on_rewind: Callable[[int], None],
    ):
        super().__init__()
        self.checkpoints = list(reversed(checkpoints or []))
        self.on_rewind = on_rewind

    def _render_option(self, meta: Dict, palette: dict) -> Text:
        turn = meta.get("turn", 0)
        prompt = " ".join(str(meta.get("prompt", "")).split())[:45]
        files_count = len(meta.get("files", {}))
        out = Text(no_wrap=True, overflow="ellipsis")
        out.append("◇ ", palette["accent1"])
        out.append(f"#{turn:<3} ", f"bold {palette['text']}")
        out.append(f"{files_count} 个文件  ", palette["muted"])
        out.append(f"{prompt}", palette["dim"])
        return out

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 回退检查点"
        box.border_subtitle = (
            "↑↓ 选择 · enter 回退 · esc 返回" if self.checkpoints else "q / esc 关闭"
        )
        with box:
            if not self.checkpoints:
                yield Static(
                    "○ 暂无可用快照检查点  ·  每次 AI 修改文件前会自动创建检查点",
                    classes="dialog-empty",
                )
                return
            palette = get_palette(self.app)
            yield OptionList(
                *[Option(self._render_option(cp, palette)) for cp in self.checkpoints],
                id="rewind-list",
            )

    def on_mount(self) -> None:
        if self.checkpoints:
            options = self.query_one(OptionList)
            options.focus()
            options.highlighted = 0

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if not self.checkpoints:
            return
        turn = self.checkpoints[event.option_index].get("turn", 0)
        self.on_rewind(turn)
        self.app.pop_screen()


__all__ = ["RewindPickerScreen"]
