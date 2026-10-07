"""Model picker screen."""

from __future__ import annotations

from typing import Callable, List

from textual.screen import Screen
from textual.widgets import SelectionList, Static


class ModelPickerScreen(Screen):
    """Pick a configured model; Enter switches and dismisses."""

    BINDINGS = [
        ("escape", "app.pop_screen", "返回"),
        ("enter", "select_current", "选择"),
    ]

    def __init__(self, *, models: List[str], on_select: Callable[[str], None]):
        super().__init__()
        self.models = list(models)
        self.on_select = on_select

    def compose(self):
        yield Static("选择模型 · Enter 切换 · Esc 返回", classes="picker-title")
        yield SelectionList(
            *[(model, model) for model in self.models],
            id="model-list",
        )

    def on_mount(self) -> None:
        self.query_one(SelectionList).focus()

    def action_select_current(self) -> None:
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


__all__ = ["ModelPickerScreen"]
