"""Session picker screen."""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from rich.text import Text
from textual.screen import Screen
from textual.widgets import SelectionList, Static


def _label(session: Dict[str, Any]) -> str:
    name = session.get("name", "?")
    count = session.get("message_count", 0)
    model = session.get("model", "?")
    created = str(session.get("created_at", ""))[:16]
    return f"{name}   ({count} msgs · {model} · {created})"


class SessionPickerScreen(Screen):
    """Pick a saved session; Enter loads and dismisses."""

    BINDINGS = [
        ("escape", "app.pop_screen", "返回"),
        ("enter", "select_current", "选择"),
    ]

    def __init__(
        self, *, sessions: List[Dict[str, Any]], on_select: Callable[[str], None]
    ):
        super().__init__()
        self.sessions = list(sessions)
        self.on_select = on_select

    def compose(self):
        yield Static("历史会话 · Enter 载入 · Esc 返回", classes="picker-title")
        if not self.sessions:
            yield Static("(no saved sessions)", id="session-empty")
            return
        yield SelectionList(
            *[
                (Text(_label(session)), session.get("name", ""))
                for session in self.sessions
            ],
            id="session-list",
        )

    def on_mount(self) -> None:
        if self.sessions:
            self.query_one(SelectionList).focus()

    def action_select_current(self) -> None:
        if self.sessions:
            self.query_one(SelectionList).action_select()

    def on_selection_list_selected_changed(
        self, event: SelectionList.SelectedChanged
    ) -> None:
        event.stop()
        selected = event.selection_list.selected
        if not selected:
            return
        self.on_select(selected[0])
        self.app.pop_screen()


__all__ = ["SessionPickerScreen"]
