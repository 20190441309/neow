"""Workspace file picker screen for /add."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List, Optional

from rich.text import Text
from textual import events
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from neow.tui.theme import get_palette

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


def scan_workspace_files(
    root: Optional[Path] = None, max_files: int = 400
) -> List[str]:
    base = root or Path.cwd()
    results = []
    try:
        for cur, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for f in files:
                if f.startswith("."):
                    continue
                full = Path(cur) / f
                try:
                    rel = str(full.relative_to(base)).replace("\\", "/")
                    results.append(rel)
                    if len(results) >= max_files:
                        return results
                except ValueError:
                    continue
    except Exception:
        pass
    return sorted(results)


class FilePickerScreen(ModalScreen):
    """Search and pick a workspace file to add to context."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    FilePickerScreen .dialog {
        width: 78;
    }
    FilePickerScreen #file-search {
        margin-bottom: 1;
    }
    FilePickerScreen OptionList {
        height: auto;
        max-height: 14;
    }
    """

    def __init__(
        self,
        *,
        on_add: Optional[Callable[[str], None]] = None,
        on_select: Optional[Callable[[str], None]] = None,
        root: Optional[Path] = None,
        workspace_root: Optional[Path] = None,
    ):
        super().__init__()
        self.on_add = on_add or on_select or (lambda p: None)
        base = root or workspace_root
        self.all_files = scan_workspace_files(base)
        self.visible_files = list(self.all_files)

    def _render_option(self, path: str, palette: dict) -> Text:
        out = Text(no_wrap=True, overflow="ellipsis")
        out.append("◇ ", palette["accent1"])
        if "/" in path:
            folder, name = path.rsplit("/", 1)
            out.append(f"{folder}/", palette["muted"])
            out.append(name, f"bold {palette['text']}")
        else:
            out.append(path, f"bold {palette['text']}")
        return out

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 添加上下文文件"
        box.border_subtitle = "输入筛选 · ↑↓ 选择 · enter 添加 · esc 返回"
        with box:
            yield Input(placeholder="搜索文件路径…", id="file-search")
            palette = get_palette(self.app)
            options = [
                Option(self._render_option(f, palette)) for f in self.visible_files
            ]
            empty_Static = Static(
                "○ 未找到匹配的文件", classes="dialog-empty", id="file-empty"
            )
            empty_Static.display = len(options) == 0
            yield empty_Static
            yield OptionList(*options, id="file-list")

    def on_mount(self) -> None:
        self.query_one(Input).focus()
        if self.visible_files:
            self.query_one(OptionList).highlighted = 0

    def on_key(self, event: events.Key) -> None:
        if event.key in ("down", "up") and self.visible_files:
            options = self.query_one(OptionList)
            idx = options.highlighted if options.highlighted is not None else 0
            if event.key == "down":
                options.highlighted = min(len(self.visible_files) - 1, idx + 1)
            else:
                options.highlighted = max(0, idx - 1)
            event.stop()

    def on_input_changed(self, event: Input.Changed) -> None:
        query = event.value.strip().lower()
        if not query:
            self.visible_files = list(self.all_files)
        else:
            self.visible_files = [f for f in self.all_files if query in f.lower()]
        options_widget = self.query_one(OptionList)
        options_widget.clear_options()
        palette = get_palette(self.app)
        for f in self.visible_files:
            options_widget.add_option(Option(self._render_option(f, palette)))
        if self.visible_files:
            options_widget.highlighted = 0
        empty_widget = self.query_one("#file-empty", Static)
        empty_widget.display = len(self.visible_files) == 0

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        text = event.value.strip()
        options = self.query_one(OptionList)
        idx = options.highlighted if options.highlighted is not None else 0
        if self.visible_files and 0 <= idx < len(self.visible_files):
            self.on_add(self.visible_files[idx])
            self.app.pop_screen()
        elif text:
            self.on_add(text)
            self.app.pop_screen()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if 0 <= event.option_index < len(self.visible_files):
            self.on_add(self.visible_files[event.option_index])
            self.app.pop_screen()


__all__ = ["FilePickerScreen", "scan_workspace_files"]
