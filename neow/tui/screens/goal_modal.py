"""Autonomous goal mode modal screen for /goal."""

from __future__ import annotations

from typing import Callable, Optional

from rich.text import Text
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from neow.core.goal import GoalState
from neow.tui.theme import get_palette


class GoalModalScreen(ModalScreen):
    """Configure, start, or stop autonomous /goal execution mode."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    GoalModalScreen .dialog {
        width: 76;
    }
    GoalModalScreen #goal-status {
        margin-bottom: 1;
    }
    GoalModalScreen #goal-desc {
        margin-bottom: 1;
    }
    GoalModalScreen #goal-input {
        margin-top: 0;
    }
    """

    def __init__(
        self,
        *,
        active_goal: Optional[GoalState] = None,
        on_start: Callable[[str], None],
        on_stop: Optional[Callable[[], None]] = None,
    ):
        super().__init__()
        self.active_goal = active_goal if (active_goal and active_goal.active) else None
        self.on_start = on_start
        self.on_stop = on_stop

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 自主目标模式 (Goal)"
        box.border_subtitle = "enter 启动 · esc 返回"
        palette = get_palette(self.app)
        with box:
            if self.active_goal is not None:
                status = Text()
                status.append("● ", style=palette["success"])
                status.append(
                    f"正在执行目标 (第 {self.active_goal.current_round}/"
                    f"{self.active_goal.max_rounds} 轮): ",
                    style=f"bold {palette['text']}",
                )
                status.append(self.active_goal.goal, style=palette["accent1"])
                yield Static(status, id="goal-status")

            desc = Text()
            desc.append("◇ 执行机制  ", style=palette["accent2"])
            desc.append(
                "自动拆解子任务 (todo_write) · 多轮持续推进与测试验证 · 直至目标 100% 达成",
                style=palette["muted"],
            )
            yield Static(desc, id="goal-desc", classes="dialog-block")

            yield Input(
                placeholder="输入最终目标，例如：修复全部单元测试并确保 flake8 零警告…",
                id="goal-input",
            )
            with Horizontal(classes="actions"):
                yield Button("启动目标", variant="primary", id="start-goal-btn")
                if self.active_goal is not None and self.on_stop is not None:
                    yield Button("停止当前目标", variant="error", id="stop-goal-btn")
                yield Button("取消", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#goal-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.app.pop_screen()
        elif event.button.id == "stop-goal-btn":
            self.app.pop_screen()
            if self.on_stop is not None:
                self.on_stop()
        elif event.button.id == "start-goal-btn":
            self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        val = self.query_one("#goal-input", Input).value.strip()
        if val:
            self.app.pop_screen()
            self.on_start(val)


__all__ = ["GoalModalScreen"]
