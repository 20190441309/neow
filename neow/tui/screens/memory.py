"""Memory viewer and editor screen for /memory."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from rich.text import Text
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from neow.tui.theme import get_palette


class MemoryScreen(ModalScreen):
    """View and add long-term project memory notes."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    MemoryScreen .dialog {
        width: 78;
        height: auto;
        max-height: 82%;
    }
    MemoryScreen #memory-path {
        margin-bottom: 1;
    }
    MemoryScreen #memory-scroll {
        height: auto;
        max-height: 12;
        margin-bottom: 1;
    }
    MemoryScreen #new-note-input {
        margin-top: 0;
    }
    """

    def __init__(
        self,
        *,
        notes: List[str],
        memory_path: Optional[Path] = None,
        on_add_note: Optional[Callable[[str], None]] = None,
    ):
        super().__init__()
        self.notes = list(notes)
        self.memory_path = memory_path or (Path.cwd() / ".neow" / "memory.md")
        self.on_add_note = on_add_note

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 项目记忆"
        box.border_subtitle = "enter 添加 · esc 返回"
        palette = get_palette(self.app)
        with box:
            path_info = Text("◇ 存储路径  ", style=palette["muted"])
            path_info.append(str(self.memory_path), style=palette["dim"])
            yield Static(path_info, id="memory-path")
            with VerticalScroll(id="memory-scroll", classes="dialog-block"):
                if self.notes:
                    for i, note in enumerate(self.notes, 1):
                        note_text = Text(f"{i:>2}. ", style=palette["accent2"])
                        note_text.append(note.strip(), style=palette["text"])
                        yield Static(note_text)
                else:
                    yield Static(
                        "○ 暂无记忆笔记 · 在下方输入项目约定或偏好即可持久化保存",
                        classes="dialog-empty",
                    )
            yield Input(
                placeholder="新增记忆笔记，例如: 统一使用 pytest，禁止使用 unittest…",
                id="new-note-input",
            )
            with Horizontal(classes="actions"):
                yield Button("添加记忆", variant="primary", id="add-note-btn")
                yield Button("返回", id="close-btn")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.app.pop_screen()
        elif event.button.id == "add-note-btn":
            self._save_note()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._save_note()

    def _save_note(self) -> None:
        val = self.query_one(Input).value.strip()
        if val and self.on_add_note:
            self.on_add_note(val)
            self.app.pop_screen()


__all__ = ["MemoryScreen"]
