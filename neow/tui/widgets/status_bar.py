"""Top bar and status bar widgets."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

from rich.text import Text
from textual.containers import Horizontal
from textual.widgets import Static

from neow.tui.effects.spinner import BRAILLE_FRAMES
from neow.tui.theme import widget_palette
from neow.tui.widgets.logo import NeowLogo

SEPARATOR = "  │  "
IDLE = "idle"

_MODE_KEYS = {"always-ask": "success", "write": "warn", "yolo": "error"}


def _git_branch() -> Optional[str]:
    """Best-effort current git branch; None outside a repo."""

    try:
        from neow.tools.git import _run_git

        branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
        return branch or None
    except Exception:
        return None


def short_path(path: Path, limit: int = 36) -> str:
    """``~``-relative path, keeping the tail when it exceeds *limit*."""

    text = str(path)
    home = os.path.expanduser("~")
    if home and home != "/" and (text == home or text.startswith(home + os.sep)):
        text = "~" + text[len(home) :]
    if len(text) <= limit:
        return text
    parts = Path(text).parts
    tail = os.sep.join(parts[-2:]) if len(parts) >= 2 else text
    return f"…{os.sep}{tail}"


def human_tokens(count: int) -> str:
    if count < 1000:
        return str(count)
    if count < 1_000_000:
        return f"{count / 1000:.1f}k"
    return f"{count / 1_000_000:.2f}M"


class TopBar(Horizontal):
    """One-line chrome: logo, model, branch, approval mode; cwd on the right."""

    def compose(self):
        yield NeowLogo(effects=getattr(self.app, "effects", "full"))
        yield Static(id="topbar-info")
        yield Static(id="topbar-cwd")

    def on_mount(self) -> None:
        self.refresh_info()

    def refresh_info(self) -> None:
        palette = widget_palette(self)
        app = self.app
        conversation = getattr(app, "conversation", None)
        model = getattr(getattr(conversation, "model_client", None), "model", "unknown")
        info = Text(no_wrap=True, overflow="ellipsis")
        info.append(SEPARATOR, palette["border_strong"])
        info.append(str(model), f"bold {palette['accent2']}")

        branch = _git_branch()
        if branch:
            info.append(SEPARATOR, palette["border_strong"])
            info.append("git:", palette["muted"])
            info.append(branch, palette["dim"])

        policy = getattr(app, "approval_policy", None)
        if policy is not None:
            mode = str(getattr(policy.mode, "value", policy.mode))
            info.append(SEPARATOR, palette["border_strong"])
            info.append("● ", palette[_MODE_KEYS.get(mode, "warn")])
            info.append(mode, palette["dim"])

        self.query_one("#topbar-info", Static).update(info)
        self.query_one("#topbar-cwd", Static).update(
            Text(short_path(Path.cwd()), style=palette["muted"])
        )


class StatusBar(Static):
    """One-line footer: activity on the left; tokens, cost, context right."""

    def __init__(self, *args, **kwargs):
        super().__init__("", *args, **kwargs)
        self._input_tokens = 0
        self._output_tokens = 0
        self._cost: Optional[float] = None
        self._context_pct: Optional[float] = None
        self._activity = IDLE
        self._busy_since: Optional[float] = None
        self._frame = 0
        self._timer = None

    def on_mount(self) -> None:
        self._refresh()

    def on_resize(self) -> None:
        self._refresh()

    def set_tokens(
        self,
        input_tokens: int,
        output_tokens: int,
        cost: Optional[float] = None,
    ) -> None:
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._cost = cost
        self._refresh()

    def set_context(self, pct: float) -> None:
        self._context_pct = pct
        self._refresh()

    def set_activity(self, text: str) -> None:
        busy = text != IDLE
        if busy and self._busy_since is None:
            self._busy_since = time.monotonic()
        if not busy:
            self._busy_since = None
        self._activity = text
        self._sync_timer(busy)
        self._refresh()

    def _sync_timer(self, busy: bool) -> None:
        animate = busy and getattr(self.app, "effects", "full") != "off"
        if animate and self._timer is None and self.is_mounted:
            self._timer = self.set_interval(0.1, self._tick)
        elif not animate and self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _tick(self) -> None:
        self._frame += 1
        self._refresh()

    def _refresh(self) -> None:
        self.update(self._render_text())

    def _render_left(self, palette) -> Text:
        out = Text()
        if self._activity == IDLE:
            out.append("○ ", palette["muted"])
            out.append(IDLE, palette["muted"])
            return out
        spinner = BRAILLE_FRAMES[self._frame % len(BRAILLE_FRAMES)]
        out.append(f"{spinner} ", f"bold {palette['accent2']}")
        out.append(self._activity, palette["accent2"])
        if self._busy_since is not None:
            elapsed = int(time.monotonic() - self._busy_since)
            out.append(f"  {elapsed}s", palette["muted"])
        return out

    def _render_right(self, palette) -> Text:
        out = Text()
        out.append("↑ ", palette["muted"])
        out.append(human_tokens(self._input_tokens), palette["dim"])
        out.append("  ↓ ", palette["muted"])
        out.append(human_tokens(self._output_tokens), palette["dim"])
        if self._cost is not None:
            out.append("  ·  ", palette["border_strong"])
            out.append(f"${self._cost:.4f}", palette["success"])
        if self._context_pct is not None:
            pct = self._context_pct
            key = "error" if pct >= 80 else "warn" if pct >= 50 else "dim"
            out.append("  ·  ", palette["border_strong"])
            out.append("ctx ", palette["muted"])
            out.append(f"{pct:.0f}%", palette[key])
        return out

    def _render_text(self) -> Text:
        palette = widget_palette(self)
        left = self._render_left(palette)
        right = self._render_right(palette)
        width = self.content_size.width if self.is_mounted else 0
        gap = max(width - left.cell_len - right.cell_len, 3)
        return Text.assemble(left, " " * gap, right, no_wrap=True, overflow="ellipsis")


__all__ = ["TopBar", "StatusBar", "NeowLogo", "short_path", "human_tokens"]
