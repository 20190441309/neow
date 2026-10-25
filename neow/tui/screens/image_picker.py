"""Image file picker screen for /image."""

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

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}


def scan_workspace_images(
    root: Optional[Path] = None, max_images: int = 100
) -> List[str]:
    base = root or Path.cwd()
    results = []
    try:
        for cur, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for f in files:
                if Path(f).suffix.lower() in IMAGE_EXTS:
                    full = Path(cur) / f
                    try:
                        rel = str(full.relative_to(base)).replace("\\", "/")
                        results.append(rel)
                        if len(results) >= max_images:
                            return results
                    except ValueError:
                        continue
    except Exception:
        pass
    return sorted(results)


class ImagePickerScreen(ModalScreen):
    """Pick or input an image path to add to conversation."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    ImagePickerScreen .dialog {
        width: 76;
    }
    ImagePickerScreen #img-search {
        margin-bottom: 1;
    }
    ImagePickerScreen OptionList {
        height: auto;
        max-height: 10;
    }
    """

    def __init__(
        self,
        *,
        on_select: Callable[[str], None],
        root: Optional[Path] = None,
        workspace_root: Optional[Path] = None,
    ):
        super().__init__()
        self.on_select = on_select
        base = root or workspace_root
        self.images = scan_workspace_images(base)

    def _render_option(self, path: str, palette: dict) -> Text:
        out = Text(no_wrap=True, overflow="ellipsis")
        out.append("◇ ", palette["accent3"])
        out.append(path, f"bold {palette['text']}")
        return out

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 添加图片"
        box.border_subtitle = "输入路径 · ↑↓ 选择 · enter 载入 · esc 返回"
        with box:
            yield Input(
                placeholder="输入图片文件路径 (png / jpg / webp)…", id="img-search"
            )
            palette = get_palette(self.app)
            if self.images:
                yield OptionList(
                    *[Option(self._render_option(img, palette)) for img in self.images],
                    id="img-list",
                )
            else:
                yield Static(
                    "○ 工作区未扫描到图片文件 · 请在上方直接输入图片路径",
                    classes="dialog-empty",
                )

    def on_mount(self) -> None:
        self.query_one(Input).focus()
        if self.images:
            self.query_one(OptionList).highlighted = 0

    def on_key(self, event: events.Key) -> None:
        if event.key in ("down", "up") and self.images:
            options = self.query_one(OptionList)
            idx = options.highlighted if options.highlighted is not None else 0
            if event.key == "down":
                options.highlighted = min(len(self.images) - 1, idx + 1)
            else:
                options.highlighted = max(0, idx - 1)
            event.stop()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        path = event.value.strip()
        if path:
            self.on_select(path)
            self.app.pop_screen()
        elif self.images:
            options = self.query_one(OptionList)
            idx = options.highlighted if options.highlighted is not None else 0
            self.on_select(self.images[idx])
            self.app.pop_screen()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if 0 <= event.option_index < len(self.images):
            self.on_select(self.images[event.option_index])
            self.app.pop_screen()


__all__ = ["ImagePickerScreen", "scan_workspace_images"]
