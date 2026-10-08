"""Session picker screen."""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from rich.text import Text
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from neow.tui.theme import get_palette


def _label(session: Dict[str, Any], palette: Dict[str, Any]) -> Text:
    name = session.get("name", "?")
    count = session.get("message_count", 0)
    model = session.get("model", "?")
    created = str(session.get("created_at", ""))[:16].replace("T", " ")
    out = Text(no_wrap=True, overflow="ellipsis")
    out.append("◇ ", palette["accent2"])
    out.append(str(name), f"bold {palette['text']}")
    out.append(f"   {count} msgs · {model} · {created}", palette["muted"])
    return out


class SessionPickerScreen(ModalScreen):
    """Pick a saved session; Enter loads and dismisses."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]

    def __init__(
        self, *, sessions: List[Dict[str, Any]], on_select: Callable[[str], None]
    ):
        super().__init__()
        self.sessions = list(sessions)
        self.on_select = on_select

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "历史会话"
        box.border_subtitle = "enter 载入 · esc 返回"
        with box:
            if not self.sessions:
                yield Static(
                    "还没有保存的会话 · /save [name] 保存当前会话",
                    id="session-empty",
                    classes="dialog-empty",
                )
                return
            palette = get_palette(self.app)
            yield OptionList(
                *[
                    Option(_label(session, palette)) for session in self.sessions
                ],
                id="session-list",
            )

    def on_mount(self) -> None:
        if self.sessions:
            options = self.query_one(OptionList)
            options.focus()
            options.highlighted = 0

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        name = str(self.sessions[event.option_index].get("name", ""))
        if not name:
            return
        self.on_select(name)
        self.app.pop_screen()


__all__ = ["SessionPickerScreen"]
