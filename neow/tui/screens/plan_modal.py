"""Interactive execution plan modal for /plan."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from rich.text import Text
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from neow.tui.theme import get_palette


class PlanModalScreen(ModalScreen):
    """Review, create, or approve a step-by-step execution plan (/plan)."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    PlanModalScreen .dialog {
        width: 78;
        max-height: 28;
    }
    PlanModalScreen #plan-steps {
        max-height: 12;
        margin-bottom: 1;
    }
    PlanModalScreen #plan-input {
        margin-top: 0;
    }
    """

    def __init__(
        self,
        *,
        todos: Optional[List[Dict[str, str]]] = None,
        initial_task: str = "",
        on_approve: Callable[[str], None],
        on_generate: Optional[Callable[[str], None]] = None,
    ):
        super().__init__()
        self.todos = list(todos or [])
        self.initial_task = initial_task
        self.on_approve = on_approve
        self.on_generate = on_generate

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 计划审批模式 (Plan)"
        box.border_subtitle = "enter 生成/执行 · esc 返回"
        palette = get_palette(self.app)
        with box:
            with VerticalScroll(id="plan-steps", classes="dialog-block"):
                if self.todos:
                    lines = Text()
                    lines.append(
                        f"当前共有 {len(self.todos)} 个计划步骤：\n",
                        style=f"bold {palette['accent1']}",
                    )
                    for idx, item in enumerate(self.todos, 1):
                        status = item.get("status", "pending")
                        glyph = (
                            "●"
                            if status == "completed"
                            else ("▸" if status == "in_progress" else "○")
                        )
                        color = (
                            palette["success"]
                            if status == "completed"
                            else (
                                palette["accent1"]
                                if status == "in_progress"
                                else palette["muted"]
                            )
                        )
                        lines.append(f"  {glyph} {idx}. ", style=color)
                        lines.append(
                            f"{item.get('content', '')}\n", style=palette["text"]
                        )
                    yield Static(lines)
                else:
                    hint = Text()
                    hint.append("◇ 先规划后执行  ", style=palette["accent2"])
                    hint.append(
                        "输入任务需求后，Agent 将首先拆解步骤清单并等待确认，避免盲目修改代码。",
                        style=palette["muted"],
                    )
                    yield Static(hint)

            yield Input(
                value=self.initial_task,
                placeholder="输入需要规划的任务（或留空直接批准执行当前步骤）…",
                id="plan-input",
            )
            with Horizontal(classes="actions"):
                if self.todos:
                    yield Button("批准并执行", variant="primary", id="approve-plan-btn")
                yield Button(
                    "生成/更新计划",
                    variant="primary" if not self.todos else "default",
                    id="generate-plan-btn",
                )
                yield Button("取消", id="cancel-plan-btn")

    def on_mount(self) -> None:
        self.query_one("#plan-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-plan-btn":
            self.app.pop_screen()
        elif event.button.id == "approve-plan-btn":
            task = self.query_one("#plan-input", Input).value.strip()
            self.app.pop_screen()
            self.on_approve(task)
        elif event.button.id == "generate-plan-btn":
            self._submit_generate()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        val = self.query_one("#plan-input", Input).value.strip()
        if not val and self.todos:
            self.app.pop_screen()
            self.on_approve("")
        else:
            self._submit_generate()

    def _submit_generate(self) -> None:
        val = self.query_one("#plan-input", Input).value.strip()
        if val:
            self.app.pop_screen()
            if self.on_generate is not None:
                self.on_generate(val)
            else:
                self.on_approve(val)


__all__ = ["PlanModalScreen"]
