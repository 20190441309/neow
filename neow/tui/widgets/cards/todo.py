"""Task list card: one per turn, updated in place by ``todo_write``."""

from __future__ import annotations

from typing import Dict, List

from rich.text import Text
from textual.widgets import Static

from neow.core.todos import MARKS, format_todos, todo_summary
from neow.tui.theme import MIDNIGHT, widget_palette
from neow.tui.widgets.cards.base import CardBase


def render_todos(todos: List[Dict[str, str]], palette: Dict[str, str]) -> Text:
    """Checklist with the active task highlighted and finished ones dimmed."""
    out = Text()
    styles = {
        "pending": (palette["muted"], palette["text"]),
        "in_progress": (f"bold {palette['accent1']}", f"bold {palette['text']}"),
        "completed": (palette["success"], f"strike {palette['dim']}"),
    }
    for index, todo in enumerate(todos):
        if index:
            out.append("\n")
        mark_style, text_style = styles[todo["status"]]
        out.append(f"{MARKS[todo['status']]} ", mark_style)
        out.append(todo["content"], text_style)
    return out


class TodoCard(CardBase):
    accent_key = "accent4"
    title_key = "dim"
    title_bold = False

    def __init__(self, todos: List[Dict[str, str]]):
        super().__init__(title="Todos", icon="☰", accent=MIDNIGHT["accent4"])
        self.todos: List[Dict[str, str]] = []
        self._list = Static(Text())
        self.add_body(self._list)
        self.update_todos(todos)

    def update_todos(self, todos: List[Dict[str, str]]) -> None:
        self.todos = [dict(t) for t in todos]
        self._body_texts[0] = format_todos(self.todos)
        self.set_title(meta=todo_summary(self.todos) if self.todos else "")
        self._list.update(render_todos(self.todos, widget_palette(self)))

    def on_mount(self) -> None:
        super().on_mount()
        self._list.update(render_todos(self.todos, widget_palette(self)))


__all__ = ["TodoCard", "render_todos"]
