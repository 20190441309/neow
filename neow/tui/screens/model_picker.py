"""Model picker screen."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from rich.text import Text
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, Static
from textual.widgets.option_list import Option

from neow.tui.theme import get_palette


class ModelPickerScreen(ModalScreen):
    """Pick a configured model; Enter switches and dismisses."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    ModelPickerScreen #model-search { margin-bottom: 1; }
    ModelPickerScreen .model-actions { height: 3; margin-top: 1; }
    ModelPickerScreen Button { margin-right: 1; min-width: 12; }
    ModelPickerScreen #model-message { height: auto; }
    """

    def __init__(
        self,
        *,
        models: List[str],
        on_select: Callable[[str], None],
        labels: Optional[Dict[str, str]] = None,
        current: Optional[str] = None,
        on_add: Optional[Callable[[], None]] = None,
        on_edit: Optional[Callable[[str], None]] = None,
        on_sync: Optional[Callable[[], None]] = None,
    ):
        super().__init__()
        self.models = list(models)
        self.labels = dict(labels or {})
        self.on_select = on_select
        self.current = current
        self.on_add = on_add
        self.on_edit = on_edit
        self.on_sync = on_sync
        self.visible_models = list(models)

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "选择模型"
        box.border_subtitle = "↑↓ 选择 · enter 切换 · esc 返回"
        with box:
            yield Input(placeholder="搜索模型", id="model-search")
            yield OptionList(
                *[Option(self._label(model)) for model in self.models],
                id="model-list",
            )
            yield Static("", id="model-message", markup=False)
            with Horizontal(classes="model-actions"):
                if self.on_add:
                    yield Button("+ BYOK", id="model-add")
                if self.on_edit:
                    yield Button("编辑", id="model-edit")
                if self.on_sync:
                    yield Button("Magpie 同步", id="model-sync")

    def _label(self, model: str) -> Text:
        palette = get_palette(self.app)
        active = model == self.current
        out = Text()
        out.append("● " if active else "  ", palette["success"])
        out.append(model, f"bold {palette['text']}" if active else palette["text"])
        label = self.labels.get(model, "")
        if label and label != model:
            extra = label[len(model) :].strip() if label.startswith(model) else label
            out.append(f"  {extra}", palette["muted"])
        if active:
            out.append("  当前", palette["success"])
        return out

    def on_mount(self) -> None:
        options = self.query_one(OptionList)
        options.focus()
        if self.current in self.models:
            options.highlighted = self.models.index(self.current)
        elif self.models:
            options.highlighted = 0

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if not self.visible_models:
            return
        self.on_select(self.visible_models[event.option_index])
        self.app.pop_screen()

    def on_input_changed(self, event: Input.Changed) -> None:
        query = event.value.strip().lower()
        self.visible_models = [
            name
            for name in self.models
            if query in name.lower() or query in self.labels.get(name, "").lower()
        ]
        self._refresh_options()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.query_one(OptionList).focus()

    def _refresh_options(self) -> None:
        options = self.query_one(OptionList)
        options.clear_options()
        options.add_options([Option(self._label(name)) for name in self.visible_models])
        if self.visible_models:
            options.highlighted = (
                self.visible_models.index(self.current)
                if self.current in self.visible_models
                else 0
            )

    def update_models(self, models: List[str], labels: Dict[str, str]) -> None:
        self.models = list(models)
        self.labels = dict(labels)
        self.on_input_changed(
            Input.Changed(self.query_one(Input), self.query_one(Input).value)
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "model-add" and self.on_add:
            self.on_add()
        elif event.button.id == "model-sync" and self.on_sync:
            self.on_sync()
        elif event.button.id == "model-edit" and self.on_edit:
            index = self.query_one(OptionList).highlighted
            if index is not None and index < len(self.visible_models):
                self.on_edit(self.visible_models[index])


__all__ = ["ModelPickerScreen"]
