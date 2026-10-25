"""Background tasks manager modal for /tasks."""

from __future__ import annotations

from typing import Optional

from rich.text import Text
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, Static
from textual.widgets.option_list import Option

from neow.core.background_tasks import BackgroundTaskManager, get_background_manager
from neow.tui.theme import get_palette


class TasksModalScreen(ModalScreen):
    """View, start, or stop background processes (/tasks)."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    TasksModalScreen .dialog {
        width: 80;
        max-height: 30;
    }
    TasksModalScreen #tasks-list {
        max-height: 8;
        margin-bottom: 1;
    }
    TasksModalScreen #tasks-output {
        max-height: 10;
        margin-bottom: 1;
    }
    """

    def __init__(self, *, manager: Optional[BackgroundTaskManager] = None):
        super().__init__()
        self.manager = manager or get_background_manager()
        self._selected_id: Optional[str] = None

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 后台任务 (Tasks)"
        box.border_subtitle = "↑↓ 查看日志 · enter 启动新任务 · esc 返回"
        with box:
            yield OptionList(id="tasks-list")
            with VerticalScroll(id="tasks-output", classes="dialog-block"):
                yield Static("", id="tasks-log-text")
            yield Input(
                placeholder="输入需要在后台运行的命令（如 npm run dev / pytest -f）…",
                id="task-cmd-input",
            )
            with Horizontal(classes="actions"):
                yield Button("启动后台任务", variant="primary", id="start-task-btn")
                yield Button("停止选中任务", variant="error", id="stop-task-btn")
                yield Button("刷新", id="refresh-tasks-btn")
                yield Button("关闭", id="close-tasks-btn")

    def on_mount(self) -> None:
        self._refresh_view()
        self.query_one("#task-cmd-input", Input).focus()

    def _refresh_view(self) -> None:
        palette = get_palette(self.app)
        opt_list = self.query_one("#tasks-list", OptionList)
        opt_list.clear_options()
        tasks = self.manager.list_tasks()
        if not tasks:
            opt_list.add_option(
                Option(Text(" ◇ 暂无后台任务", style=palette["muted"]), id="none")
            )
            self._selected_id = None
            self.query_one("#tasks-log-text", Static).update(
                Text(
                    "后台启动的服务或监控命令将在此处显示实时输出。",
                    style=palette["muted"],
                )
            )
            return

        for t in tasks:
            running = t.is_running
            glyph = "●" if running else "○"
            color = palette["success"] if running else palette["muted"]
            status_str = "运行中" if running else f"已退出({t.returncode})"
            line = Text()
            line.append(f" {glyph} {t.task_id:<6} ", style=f"bold {color}")
            line.append(f"[{status_str}] ", style=color)
            line.append(f"{int(t.elapsed_seconds)}s  ", style=palette["muted"])
            line.append(t.command, style=palette["text"])
            opt_list.add_option(Option(line, id=t.task_id))

        if self._selected_id is None or self.manager.get(self._selected_id) is None:
            self._selected_id = tasks[-1].task_id
        self._show_task_log(self._selected_id)

    def _show_task_log(self, task_id: Optional[str]) -> None:
        palette = get_palette(self.app)
        if not task_id:
            return
        task = self.manager.get(task_id)
        if task is None:
            return
        tail_lines = "\n".join(task.tail(25)) or "(暂无输出)"
        header = f"▸ {task.task_id} ({task.command}) 最近输出：\n"
        txt = Text()
        txt.append(header, style=f"bold {palette['accent1']}")
        txt.append(tail_lines, style=palette["text"])
        self.query_one("#tasks-log-text", Static).update(txt)

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        opt_id = event.option.id
        if opt_id and opt_id != "none":
            self._selected_id = opt_id
            self._show_task_log(opt_id)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._start_from_input()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "close-tasks-btn":
            self.app.pop_screen()
        elif bid == "refresh-tasks-btn":
            self._refresh_view()
        elif bid == "stop-task-btn":
            if self._selected_id:
                self.manager.stop(self._selected_id)
                self._refresh_view()
        elif bid == "start-task-btn":
            self._start_from_input()

    def _start_from_input(self) -> None:
        inp = self.query_one("#task-cmd-input", Input)
        cmd = inp.value.strip()
        if cmd:
            task = self.manager.start(cmd)
            self._selected_id = task.task_id
            inp.value = ""
            self._refresh_view()


__all__ = ["TasksModalScreen"]
