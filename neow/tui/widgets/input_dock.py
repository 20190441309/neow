"""Input dock: multiline prompt, completion, history and queue UI."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import List, Optional

from rich.text import Text
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import OptionList, Static, TextArea
from textual.widgets.option_list import Option

SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".svn",
    ".hg",
    "venv",
    ".venv",
    "env",
    ".tox",
    "dist",
    "build",
    ".eggs",
    ".mypy_cache",
}

SLASH_COMMANDS = [
    "/help",
    "/clear",
    "/exit",
    "/model",
    "/diff",
    "/commit",
    "/undo",
    "/add",
    "/drop",
    "/ls",
    "/lint",
    "/test",
    "/architect",
    "/code",
    "/save",
    "/load",
    "/history",
    "/cost",
    "/web",
    "/think",
    "/compact",
    "/export",
    "/image",
    "/approval",
    "/tree",
    "/branch",
    "/verbose",
]

COMMAND_HINTS = {
    "/help": "快捷键与使用帮助",
    "/clear": "清空当前对话",
    "/exit": "退出",
    "/model": "选择模型",
    "/diff": "查看代码改动",
    "/commit": "提交改动",
    "/undo": "撤销上次 AI 提交",
    "/add": "添加上下文文件",
    "/drop": "移出上下文文件",
    "/ls": "查看上下文文件",
    "/lint": "检查代码",
    "/test": "运行测试",
    "/architect": "架构师模式",
    "/code": "编码模式",
    "/save": "保存会话",
    "/load": "载入会话",
    "/history": "历史会话",
    "/cost": "用量与费用",
    "/web": "读取网页",
    "/think": "查看推理",
    "/compact": "压缩上下文",
    "/export": "导出对话",
    "/image": "添加图片",
    "/approval": "审批设置",
    "/tree": "会话树",
    "/branch": "创建分支",
    "/verbose": "工具详情",
}

HINT_IDLE = "Enter 发送 · Ctrl+J 换行 · @ 文件 · / 命令 · Esc 中断"
HINT_BUSY = "生成中 · Enter 排队 · Ctrl+O 折叠 · Esc 中断"
HINT_COMPLETION = "↑↓ 选择 · Tab / Enter 补全 · Esc 收起"


class PromptArea(TextArea):
    """Single-purpose prompt editor: Enter sends, Ctrl+J inserts newline."""

    def __init__(self, dock: "InputDock"):
        super().__init__(placeholder="输入问题，或用 / 查看命令")
        self._dock = dock

    async def _on_key(self, event) -> None:
        try:
            collapse = getattr(self.app, "collapse_splash", None)
            if callable(collapse):
                collapse()
        except Exception:
            pass
        key = event.key
        if key in ("up", "down", "tab", "enter", "escape"):
            # Pasted/rapid keys can arrive before TextArea.Changed is delivered.
            self._dock._refresh_completions()
        if self._dock.completion_open and key in (
            "up",
            "down",
            "tab",
            "enter",
            "escape",
        ):
            event.stop()
            event.prevent_default()
            if key in ("up", "down"):
                self._dock.move_completion(-1 if key == "up" else 1)
            elif key == "escape":
                self._dock.dismiss_completions()
            else:
                self._dock.accept_completion()
            return
        if key in ("pageup", "pagedown"):
            timeline = getattr(self.screen, "timeline", None)
            if timeline is not None:
                event.stop()
                event.prevent_default()
                action = (
                    timeline.scroll_page_up
                    if key == "pageup"
                    else timeline.scroll_page_down
                )
                action(animate=False)
                return
        if key == "ctrl+y":
            event.stop()
            event.prevent_default()
            self._dock.post_message(InputDock.CopyRequested())
            return
        if key == "enter":
            event.stop()
            event.prevent_default()
            self._dock._submit()
            return
        if key in ("ctrl+j", "shift+enter"):
            event.stop()
            event.prevent_default()
            self.insert("\n")
            return
        if key == "up" and self.cursor_location[0] == 0:
            event.stop()
            event.prevent_default()
            self._dock._history_up()
            return
        if key == "down" and self.cursor_location[0] >= self.document.line_count - 1:
            event.stop()
            event.prevent_default()
            self._dock._history_down()
            return
        await super()._on_key(event)


class InputDock(Vertical):
    """Bottom input area with completion, history and a queue strip."""

    class Submitted(Message):
        """User submitted a prompt (not busy)."""

        def __init__(self, text: str):
            self.text = text
            super().__init__()

    class QueueChanged(Message):
        """The queued-prompt list changed."""

    class CopyRequested(Message):
        """Ctrl+Y asked the screen to copy the last code block."""

    DEFAULT_CSS = """
    InputDock {
        height: auto;
    }
    InputDock PromptArea {
        height: auto;
        max-height: 6;
        border: tall $primary;
        background: $surface;
    }
    InputDock #completions {
        display: none;
        height: auto;
        max-height: 4;
        border: none;
        background: $panel;
    }
    InputDock #input-hint {
        height: 1;
        color: $text-muted;
    }
    """

    def __init__(self, *, history_path: Optional[Path] = None, **kwargs):
        super().__init__(**kwargs)
        self._history_path = (
            Path(history_path) if history_path else Path(".neow_history")
        )
        self._history: List[str] = self._load_history()
        self._history_index: Optional[int] = None
        self._draft = ""
        self._queue: List[str] = []
        self._busy = False
        self._options: List[str] = []
        self._completion_span = None
        self._dismissed_text: Optional[str] = None
        self._file_cache: List[str] = []
        self._file_cache_at = 0.0
        self.posted_submissions: List[str] = []
        self._area = PromptArea(self)
        self._completions = OptionList(id="completions")
        self._completions.can_focus = False
        self._hint = Static(HINT_IDLE, id="input-hint")

    def compose(self):
        yield self._completions
        yield self._area
        yield self._hint

    def on_mount(self) -> None:
        self._completions.display = False
        self._area.focus()

    # -- text ----------------------------------------------------------

    def text(self) -> str:
        return self._area.text

    def set_text(self, value: str) -> None:
        self._area.text = value
        self._area.move_cursor(self._area.document.end)

    # -- submission ----------------------------------------------------

    def _submit(self) -> None:
        text = self.text().strip()
        if not text:
            return
        self._remember(text)
        self._history_index = None
        self._draft = ""
        self.dismiss_completions()
        if self._busy and not text.startswith("/"):
            self.enqueue(text)
            self.set_text("")
            return
        self.posted_submissions.append(text)
        self.post_message(self.Submitted(text))
        self.set_text("")

    # -- history -------------------------------------------------------

    def _load_history(self) -> List[str]:
        try:
            if self._history_path.exists():
                return self._history_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            pass
        return []

    def _remember(self, text: str) -> None:
        if self._history and self._history[-1] == text:
            return
        self._history.append(text)
        try:
            with self._history_path.open("a", encoding="utf-8") as handle:
                handle.write(text.replace("\n", " ") + "\n")
        except OSError:
            pass

    def _history_up(self) -> None:
        if not self.text().strip() and self._queue:
            text = self.pop_last_queued()
            if text is not None:
                self.set_text(text)
            return
        if not self._history:
            return
        if self._history_index is None:
            self._draft = self.text()
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        self.set_text(self._history[self._history_index])

    def _history_down(self) -> None:
        if self._history_index is None:
            return
        self._history_index += 1
        if self._history_index >= len(self._history):
            self._history_index = None
            self.set_text(self._draft)
        else:
            self.set_text(self._history[self._history_index])

    # -- queue ---------------------------------------------------------

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._update_hint()

    def enqueue(self, text: str) -> None:
        self._queue.append(text)
        self._queue_changed()

    def queued_count(self) -> int:
        return len(self._queue)

    def queued_texts(self) -> List[str]:
        return list(self._queue)

    def pop_first_queued(self) -> Optional[str]:
        if not self._queue:
            return None
        text = self._queue.pop(0)
        self._queue_changed()
        return text

    def pop_last_queued(self) -> Optional[str]:
        if not self._queue:
            return None
        text = self._queue.pop()
        self._queue_changed()
        return text

    def _queue_changed(self) -> None:
        self.post_message(self.QueueChanged())

    # -- completion ----------------------------------------------------

    def completion_options(self) -> List[str]:
        return list(self._options)

    def on_text_area_changed(self, event) -> None:
        self._refresh_completions()

    def on_text_area_selection_changed(self, event) -> None:
        self._refresh_completions()

    @property
    def completion_open(self) -> bool:
        return bool(self._options) and self._completions.display

    def _update_hint(self) -> None:
        self._hint.update(
            HINT_COMPLETION
            if self.completion_open
            else HINT_BUSY if self._busy else HINT_IDLE
        )

    def dismiss_completions(self) -> None:
        self._dismissed_text = self.text()
        self._completions.display = False
        self._options = []
        self._update_hint()

    def move_completion(self, delta: int) -> None:
        index = self._completions.highlighted or 0
        self._completions.highlighted = (index + delta) % len(self._options)

    def accept_completion(self) -> None:
        if not self.completion_open or self._completion_span is None:
            return
        index = self._completions.highlighted or 0
        value = self._options[index]
        start, end = self._completion_span
        text = self.text()
        suffix = text[end:]
        replacement = value + ("" if suffix.startswith(" ") else " ")
        updated = text[:start] + replacement + suffix
        self.set_text(updated)
        self._area.move_cursor(
            self._area.document.get_location_from_index(start + len(replacement))
        )
        self.dismiss_completions()
        self._area.focus()

    def _refresh_completions(self) -> None:
        text = self.text()
        if text == self._dismissed_text:
            return
        self._dismissed_text = None
        cursor = self._area.document.get_index_from_location(self._area.cursor_location)
        before = text[:cursor]
        options: List[str] = []
        match = re.search(r"(?<!\S)@([^\s]*)$", before)
        if re.fullmatch(r"/[^\s]*", before):
            options = [name for name in SLASH_COMMANDS if name.startswith(before)]
            self._completion_span = (0, cursor)
        elif match:
            options = ["@" + path for path in self._file_options(match.group(1))]
            self._completion_span = (match.start(), cursor)
        # Replace the rest of a partially edited token, not the following words.
        if options:
            end = cursor
            while end < len(text) and not text[end].isspace():
                end += 1
            self._completion_span = (self._completion_span[0], end)
        previous = self._options
        self._options = options
        if options:
            if options != previous:
                self._completions.clear_options()
                labels = [
                    (
                        Text.assemble(
                            (f"{option:<12}", "bold"), (COMMAND_HINTS[option], "dim")
                        )
                        if option in COMMAND_HINTS
                        else Text(option)
                    )
                    for option in options
                ]
                self._completions.add_options([Option(label) for label in labels])
                self._completions.highlighted = 0
            self._completions.display = True
        else:
            self._completions.display = False
        self._update_hint()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self._completions.highlighted = event.option_index
        self.accept_completion()

    def _file_options(self, prefix: str, limit: int = 20) -> List[str]:
        now = time.monotonic()
        if now - self._file_cache_at > 5.0:
            self._file_cache = self._scan_files()
            self._file_cache_at = now
        prefix_lower = prefix.lower()
        return [
            path for path in self._file_cache if path.lower().startswith(prefix_lower)
        ][:limit]

    def _scan_files(self) -> List[str]:
        """Return relative file paths under cwd (bounded scan)."""

        cwd = Path.cwd()
        results: List[str] = []
        scanned = 0
        try:
            for root, dirs, files in os.walk(cwd):
                dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS)
                scanned += 1
                for name in sorted(files):
                    results.append(str((Path(root) / name).relative_to(cwd)))
                    scanned += 1
                    if scanned >= 5000:
                        return results
                if scanned >= 5000:
                    break
        except OSError:
            pass
        return results


__all__ = ["InputDock", "PromptArea", "SLASH_COMMANDS"]
