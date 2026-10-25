"""Interactive question modal for the ask_user tool."""

from __future__ import annotations

from typing import Callable, List, Optional

from rich.text import Text
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, Static
from textual.widgets.option_list import Option

from neow.tui.theme import get_palette


class AskUserModalScreen(ModalScreen[str]):
    """Modal presented when the agent invokes ``ask_user``."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "skip", "跳过")]
    DEFAULT_CSS = """
    AskUserModalScreen .dialog {
        width: 74;
    }
    AskUserModalScreen #ask-question {
        margin-bottom: 1;
    }
    AskUserModalScreen #ask-options {
        max-height: 10;
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        *,
        question: str,
        options: Optional[List[str]] = None,
        on_answer: Optional[Callable[[str], None]] = None,
    ):
        super().__init__()
        self.question = question
        self.options = [str(o) for o in (options or []) if str(o).strip()]
        self.on_answer = on_answer

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 需要确认"
        box.border_subtitle = "↑↓ 选择或直接输入 · enter 提交 · esc 跳过"
        palette = get_palette(self.app)
        with box:
            q_text = Text()
            q_text.append("◇ ", style=palette["accent1"])
            q_text.append(self.question, style=f"bold {palette['text']}")
            yield Static(q_text, id="ask-question", classes="dialog-block")

            if self.options:
                opt_items = [
                    Option(Text(f" ○  {opt}"), id=f"opt-{idx}")
                    for idx, opt in enumerate(self.options)
                ]
                yield OptionList(*opt_items, id="ask-options")

            yield Input(
                placeholder="或者输入自定义回答…",
                id="ask-custom-input",
            )
            with Horizontal(classes="actions"):
                yield Button("提交回答", variant="primary", id="submit-ask-btn")
                yield Button("跳过", id="skip-ask-btn")

    def on_mount(self) -> None:
        if self.options:
            self.query_one("#ask-options", OptionList).focus()
        else:
            self.query_one("#ask-custom-input", Input).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        opt_id = event.option.id or ""
        if opt_id.startswith("opt-"):
            idx = int(opt_id.split("-", 1)[1])
            if 0 <= idx < len(self.options):
                self._finish(self.options[idx])

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit_from_ui()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "skip-ask-btn":
            self.action_skip()
        elif event.button.id == "submit-ask-btn":
            self._submit_from_ui()

    def _submit_from_ui(self) -> None:
        custom = self.query_one("#ask-custom-input", Input).value.strip()
        if custom:
            self._finish(custom)
            return
        if self.options:
            opt_list = self.query_one("#ask-options", OptionList)
            idx = opt_list.highlighted
            if idx is not None and 0 <= idx < len(self.options):
                self._finish(self.options[idx])
                return
        self._finish("")

    def action_skip(self) -> None:
        self._finish("")

    def _finish(self, answer: str) -> None:
        if self.on_answer is not None:
            self.on_answer(answer)
        self.dismiss(answer)


__all__ = ["AskUserModalScreen"]
