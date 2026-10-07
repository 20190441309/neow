"""Input dock: multiline prompt, completion, history and queue UI."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

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

HINT_IDLE = "Enter 发送 · Ctrl+J 换行 · @ 文件 · / 命令 · Esc 中断"
HINT_BUSY = "生成中 · Enter 排队 · Ctrl+O 折叠 · Esc 中断"


class PromptArea(TextArea):
    """Single-purpose prompt editor: Enter sends, Ctrl+J inserts newline."""

    def __init__(self, dock: "InputDock"):
        super().__init__()
        self._dock = dock

    async def _on_key(self, event) -> None:
        key = event.key
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

    DEFAULT_CSS = """
    InputDock {
        height: auto;
        max-height: 12;
    }
    InputDock PromptArea {
        height: auto;
        max-height: 6;
        border: none;
        background: #0f1117;
    }
    InputDock #completions {
        display: none;
        height: auto;
        max-height: 8;
        border: none;
        background: #151a23;
    }
    InputDock #input-hint {
        height: 1;
        color: #475569;
    }
    """

    def __init__(self, *, history_path: Optional[Path] = None, **kwargs):
        super().__init__(**kwargs)
        self._history_path = Path(history_path) if history_path else Path(".neow_history")
        self._history: List[str] = self._load_history()
        self._history_index: Optional[int] = None
        self._queue: List[str] = []
        self._busy = False
        self._options: List[str] = []
        self.posted_submissions: List[str] = []
        self._area = PromptArea(self)
        self._completions = OptionList(id="completions")
        self._hint = Static(HINT_IDLE, id="input-hint")

    def compose(self):
        yield self._area
        yield self._completions
        yield self._hint

    def on_mount(self) -> None:
        self._completions.display = False
        self._area.focus()

    # -- text ----------------------------------------------------------

    def text(self) -> str:
        return self._area.text

    def set_text(self, value: str) -> None:
        self._area.text = value

    # -- submission ----------------------------------------------------

    def _submit(self) -> None:
        text = self.text().strip()
        if not text:
            return
        if self._busy:
            self.enqueue(text)
            self.set_text("")
            return
        self._remember(text)
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
            self.set_text("")
        else:
            self.set_text(self._history[self._history_index])

    # -- queue ---------------------------------------------------------

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._hint.update(HINT_BUSY if busy else HINT_IDLE)

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

    def _refresh_completions(self) -> None:
        text = self.text()
        options: List[str] = []
        if text.startswith("/"):
            token = text.split()[0] if text.split() else text
            options = [name for name in SLASH_COMMANDS if name.startswith(token)][:20]
        else:
            tokens = text.split()
            if tokens and tokens[-1].startswith("@"):
                options = self._file_options(tokens[-1][1:])
        self._options = options
        if options:
            self._completions.clear_options()
            self._completions.add_options([Option(option) for option in options])
            self._completions.display = True
        else:
            self._completions.display = False

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        value = str(event.option.prompt)
        text = self.text()
        tokens = text.split()
        if tokens and tokens[-1].startswith("@"):
            tokens[-1] = value
            self.set_text(" ".join(tokens) + " ")
        else:
            self.set_text(value + " ")

    @staticmethod
    def _file_options(prefix: str, limit: int = 20) -> List[str]:
        cwd = Path.cwd()
        prefix_lower = prefix.lower()
        results: List[str] = []
        scanned = 0
        try:
            for path in cwd.rglob("*"):
                scanned += 1
                if scanned > 5000:
                    break
                if path.is_dir():
                    if path.name in SKIP_DIRS:
                        continue
                    continue
                if any(part in SKIP_DIRS for part in path.parts):
                    continue
                try:
                    relative = str(path.relative_to(cwd))
                except ValueError:
                    continue
                if relative.lower().startswith(prefix_lower):
                    results.append(relative)
                    if len(results) >= limit:
                        break
        except OSError:
            pass
        return results


__all__ = ["InputDock", "PromptArea", "SLASH_COMMANDS"]
