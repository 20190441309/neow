"""Task list card: one per turn, updated in place by ``todo_write``."""

from __future__ import annotations

from typing import Dict, List, Optional

from rich.text import Text
from textual.widgets import Static

from neow.core.todos import MARKS, format_todos, todo_summary
from neow.tui.effects.spinner import BRAILLE_FRAMES
from neow.tui.theme import MIDNIGHT, widget_palette
from neow.tui.widgets.cards.base import CardBase


def render_todos(
    todos: List[Dict[str, str]],
    palette: Dict[str, str],
    *,
    spinner_frame: str = "",
) -> Text:
    """Checklist with the active task highlighted and finished ones dimmed.

    ``spinner_frame``, when given, replaces the static in-progress mark so
    the one task actually running reads as "running" rather than stuck.
    """
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
        mark = MARKS[todo["status"]]
        if todo["status"] == "in_progress" and spinner_frame:
            mark = spinner_frame
        out.append(f"{mark} ", mark_style)
        out.append(todo["content"], text_style)
    return out


class TodoCard(CardBase):
    accent_key = "accent4"
    title_key = "dim"
    title_bold = False

    def __init__(self, todos: List[Dict[str, str]], *, effects: str = "full"):
        super().__init__(title="Todos", icon="☰", accent=MIDNIGHT["accent4"])
        self.effects = effects
        self.todos: List[Dict[str, str]] = []
        self._list = Static(Text())
        self._spinner_index = 0
        self._timer = None
        self.add_body(self._list)
        self.update_todos(todos)

    def update_todos(self, todos: List[Dict[str, str]]) -> None:
        self.todos = [dict(t) for t in todos]
        self._body_texts[0] = format_todos(self.todos)
        self.set_title(meta=todo_summary(self.todos) if self.todos else "")
        self._sync_timer()
        self._render_list()

    def on_mount(self) -> None:
        super().on_mount()
        self._render_list()
        self._sync_timer()

    def apply_palette(self, palette) -> None:
        super().apply_palette(palette)
        self._render_list()

    # -- spinner ---------------------------------------------------------

    def _has_app(self) -> bool:
        """``True`` once attached to a running app (even mid-mount).

        ``is_mounted`` only flips true *after* ``on_mount`` returns, but
        ``self.app`` and ``set_interval`` both work during it; cards built
        before being handed to an app (e.g. in tests) have neither.
        """
        try:
            self.app
            return True
        except Exception:
            return False

    def _has_in_progress(self) -> bool:
        return any(t["status"] == "in_progress" for t in self.todos)

    def _sync_timer(self) -> None:
        animate = self.effects != "off" and self._has_in_progress() and self._has_app()
        if animate and self._timer is None:
            self._timer = self.set_interval(0.1, self._tick)
        elif not animate and self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _tick(self) -> None:
        self._spinner_index += 1
        self._render_list()

    def _spinner_frame(self) -> Optional[str]:
        if self._timer is None:
            return None
        return BRAILLE_FRAMES[self._spinner_index % len(BRAILLE_FRAMES)]

    def _render_list(self) -> None:
        if not self._has_app():
            return
        self._list.update(
            render_todos(
                self.todos,
                widget_palette(self),
                spinner_frame=self._spinner_frame() or "",
            )
        )


__all__ = ["TodoCard", "render_todos"]
