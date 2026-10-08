"""Tool call card: per-tool renderers plus a running/done/error/denied state."""

from __future__ import annotations

from typing import Any, Dict, Optional

from rich.text import Text
from textual.widgets import Static

from neow.tui.effects.spinner import BRAILLE_FRAMES
from neow.tui.theme import MIDNIGHT, widget_palette
from neow.tui.widgets.cards.base import CardBase

ACCENT_RUNNING = MIDNIGHT["tool_running"]
ACCENT_DONE = MIDNIGHT["tool_done"]
ACCENT_ERROR = MIDNIGHT["tool_error"]
MAX_BODY_LINES = 30

_STATUS_ACCENT_KEYS = {
    "pending": "tool_running",
    "running": "tool_running",
    "done": "tool_done",
    "error": "tool_error",
    "denied": "tool_error",
}


def tool_is_error(result: str) -> bool:
    return result.startswith("Error:")


def tool_is_denied(result: str) -> bool:
    return "User denied" in result


def _first_str(args: Dict[str, Any]) -> str:
    for value in args.values():
        if isinstance(value, str) and value:
            return value
    return ""


def _tool_summary(name: str, args: Dict[str, Any]) -> str:
    """One-line parameter summary for the card title (spec §5.4)."""

    if name in ("read_file",):
        return str(args.get("path") or args.get("file_path") or "")
    if name in (
        "edit_file",
        "hashline_edit",
        "write_file",
        "create_file",
        "delete_file",
    ):
        return str(args.get("file_path") or args.get("path") or "")
    if name == "execute_command":
        return str(args.get("command", ""))[:60]
    if name == "search_code":
        return str(args.get("pattern", ""))[:60]
    if name in ("web", "fetch_url"):
        return str(args.get("url", ""))[:60]
    if name == "git_commit":
        return str(args.get("message", ""))[:60]
    return _first_str(args)[:60]


def _format_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"


def render_tool_body(
    name: str,
    args: Dict[str, Any],
    result: str,
    palette: Optional[Dict[str, Any]] = None,
) -> Text:
    """Render a tool's body as rich text (design spec §5.4 table)."""

    palette = palette or MIDNIGHT
    error = palette["error"]
    success = palette["success"]
    dim = palette["dim"]
    muted = palette["muted"]
    text_style = f"bold {palette['text']}"

    out = Text()
    if name in ("edit_file", "hashline_edit"):
        old = str(args.get("old_text", ""))
        new = str(args.get("new_text", ""))
        if old or new:
            for line in old.split("\n"):
                out.append(f"- {line}\n", style=error)
            for line in new.split("\n"):
                out.append(f"+ {line}\n", style=success)
            anchor = args.get("expected_hash")
            if anchor:
                out.append(f"@ {str(anchor)[:12]}\n", style=muted)
            return out
        out.append(result or "(no diff)", style=dim)
        return out
    if name == "execute_command":
        out.append(f"$ {args.get('command', '')}\n", style=text_style)
        out.append(result or "(no output)", style=dim)
        return out
    if name == "search_code":
        matches = [line for line in result.splitlines() if line.strip()]
        out.append(f"{len(matches)} 处命中\n", style=text_style)
        out.append("\n".join(matches[:10]) or "(no matches)", style=dim)
        return out
    if name == "read_file":
        path = args.get("path") or args.get("file_path") or ""
        lines = result.count("\n") + (1 if result else 0)
        out.append(f"{path} · {lines} 行\n", style=text_style)
        out.append("\n".join(result.splitlines()[:5]), style=dim)
        return out
    if name in ("write_file", "create_file"):
        path = args.get("file_path") or ""
        lines = result.count("\n") + (1 if result else 0)
        out.append(f"{path} · {lines} 行\n", style=text_style)
        out.append("\n".join(result.splitlines()[:10]), style=dim)
        return out
    if name == "delete_file":
        out.append(f"{args.get('file_path', '')} (已删除)", style=error)
        return out
    if name in ("web", "fetch_url"):
        out.append(f"{args.get('url', '')}\n", style=text_style)
        out.append(result[:1000], style=dim)
        return out
    if name.startswith("git_") or name in ("lint", "test", "run_lint", "run_tests"):
        out.append(result[:1500] or "(no output)", style=dim)
        return out
    out.append(result or "(no output)", style=dim)
    return out


class ToolCard(CardBase):
    """A tool invocation: expanded while running, auto-collapsed when done."""

    DEFAULT_CSS = """
    ToolCard.follows {
        margin-top: 0;
    }
    ToolCard .card-body {
        margin: 0 0 0 2;
        padding: 0 1;
    }
    """

    def __init__(self, *, effects: str = "full"):
        super().__init__(
            title="Tool",
            icon="⟳",
            meta="",
            accent=ACCENT_RUNNING,
        )
        self.effects = effects
        self._name = ""
        self._args: Dict[str, Any] = {}
        self._result = ""
        self._status = "pending"
        self._user_touched = False
        self._duration: Optional[float] = None
        self._spinner_timer = None
        self._spinner_index = 0
        self._spinner_on = False
        self._body_widget = Static("", classes="tool-body")
        self.add_body(self._body_widget, "")

    # -- palette -------------------------------------------------------

    def apply_palette(self, palette) -> None:
        key = _STATUS_ACCENT_KEYS.get(self._status, "tool_running")
        if palette.get(key):
            self.set_accent(palette[key])
        self._render_body()

    def on_mount(self) -> None:
        super().on_mount()
        # Fast tools can start and finish before the card is mounted.
        self.call_after_refresh(self._render_body)

    # -- lifecycle -----------------------------------------------------

    def start(self, name: str, args: Dict[str, Any]) -> None:
        self._name = name
        self._args = dict(args or {})
        self._status = "running"
        self.set_title(title=name, icon="⟳", subtitle=_tool_summary(name, self._args))
        self.set_accent(widget_palette(self)["tool_running"])
        self._render_body()
        if self.collapsed:
            self._set_collapsed(False)
        self._spinner_on = True
        if self.effects != "off":
            self._spinner_timer = self.set_interval(0.1, self._spin)

    def _spin(self) -> None:
        if not self._spinner_on:
            return
        self._spinner_index += 1
        self.set_title(icon=self._spinner_frame())

    def _spinner_frame(self) -> str:
        return BRAILLE_FRAMES[self._spinner_index % len(BRAILLE_FRAMES)]

    def finish(
        self,
        result: str,
        is_error: bool,
        duration: Optional[float] = None,
        denied: bool = False,
    ) -> None:
        self._result = result or ""
        self._duration = duration
        self._spinner_on = False
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        if denied or tool_is_denied(self._result):
            self._status = "denied"
        elif is_error or tool_is_error(self._result):
            self._status = "error"
        else:
            self._status = "done"

        icon = {"done": "✓", "error": "✗", "denied": "⊘"}[self._status]
        palette = widget_palette(self)
        accent = palette[_STATUS_ACCENT_KEYS[self._status]]
        meta = "denied" if self._status == "denied" else ""
        if duration is not None:
            meta = _format_duration(duration)
        self.set_title(icon=icon, meta=meta)
        self.set_accent(accent)
        try:
            self.styles.animate(
                "opacity",
                0.85,
                duration=0.15,
                on_complete=lambda: self.styles.animate("opacity", 1.0, duration=0.15),
            )
        except Exception:
            pass
        self._render_body()

        if self._status == "done" and not self._user_touched and not self.collapsed:
            self._set_collapsed(True)

    def set_duration(self, seconds: float) -> None:
        self._duration = seconds
        self.set_title(meta=_format_duration(seconds))

    # -- interaction ---------------------------------------------------

    @property
    def status_icon(self) -> str:
        if self._status in ("pending", "running"):
            return "⟳"
        return self._icon

    def toggle(self) -> None:
        self._user_touched = True
        self._set_collapsed(not self.collapsed)

    def truncation_hint(self) -> str:
        if not self._result:
            return ""
        extra = len(self._result.split("\n")) - MAX_BODY_LINES
        if extra > 0:
            return f"… (+{extra} 行)"
        return ""

    # -- rendering -----------------------------------------------------

    def _render_body(self) -> None:
        palette = widget_palette(self)
        if self._status in ("pending", "running"):
            body = Text()
            if self._name == "execute_command":
                body.append(
                    f"$ {self._args.get('command', '')}\n", f"bold {palette['text']}"
                )
            body.append("运行中…", f"italic {palette['muted']}")
            if self.is_mounted:
                self._body_widget.update(body)
            return
        body = render_tool_body(self._name, self._args, self._result, palette=palette)
        lines = body.split("\n")
        if len(lines) > MAX_BODY_LINES:
            body = Text("\n").join(lines[:MAX_BODY_LINES])
            body.append(
                f"\n… (+{len(lines) - MAX_BODY_LINES} 行)",
                style=palette["muted"],
            )
        if self.is_mounted:
            self._body_widget.update(body)


__all__ = [
    "ToolCard",
    "render_tool_body",
    "tool_is_error",
    "tool_is_denied",
    "MAX_BODY_LINES",
]
