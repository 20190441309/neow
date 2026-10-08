"""Model picker screen."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from rich.text import Text
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from neow.tui.theme import get_palette


class ModelPickerScreen(ModalScreen):
    """Pick a configured model; Enter switches and dismisses."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]

    def __init__(
        self,
        *,
        models: List[str],
        on_select: Callable[[str], None],
        labels: Optional[Dict[str, str]] = None,
        current: Optional[str] = None,
    ):
        super().__init__()
        self.models = list(models)
        self.labels = dict(labels or {})
        self.on_select = on_select
        self.current = current

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "选择模型"
        box.border_subtitle = "↑↓ 选择 · enter 切换 · esc 返回"
        with box:
            if not self.models:
                yield OptionList(Option(Text("(no models configured)"), disabled=True))
                return
            yield OptionList(
                *[Option(self._label(model)) for model in self.models],
                id="model-list",
            )

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
        if not self.models:
            return
        self.on_select(self.models[event.option_index])
        self.app.pop_screen()


__all__ = ["ModelPickerScreen"]
