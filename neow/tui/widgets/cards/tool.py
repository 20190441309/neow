"""Tool call card: per-tool renderers plus a running/done/error/denied state."""

from __future__ import annotations

from typing import Any, Dict, Optional

from rich.text import Text
from textual.widgets import Static

from neow.tui.widgets.cards.base import CardBase

ACCENT_RUNNING = "#facc15"
ACCENT_DONE = "#34d399"
ACCENT_ERROR = "#f87171"
MAX_BODY_LINES = 30


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


def render_tool_body(name: str, args: Dict[str, Any], result: str) -> Text:
    """Render a tool's body as rich text (design spec §5.4 table)."""

    out = Text()
    if name in ("edit_file", "hashline_edit"):
        old = str(args.get("old_text", ""))
        new = str(args.get("new_text", ""))
        if old or new:
            for line in old.split("\n"):
                out.append(f"- {line}\n", style="#f87171")
            for line in new.split("\n"):
                out.append(f"+ {line}\n", style="#34d399")
            anchor = args.get("expected_hash")
            if anchor:
                out.append(f"@ {str(anchor)[:12]}\n", style="#64748b")
            return out
        out.append(result or "(no diff)", style="#94a3b8")
        return out
    if name == "execute_command":
        out.append(f"$ {args.get('command', '')}\n", style="bold #e5e7eb")
        out.append(result or "(no output)", style="#94a3b8")
        return out
    if name == "search_code":
        matches = [line for line in result.splitlines() if line.strip()]
        out.append(f"{len(matches)} 处命中\n", style="bold #e5e7eb")
        out.append("\n".join(matches[:10]) or "(no matches)", style="#94a3b8")
        return out
    if name == "read_file":
        path = args.get("path") or args.get("file_path") or ""
        lines = result.count("\n") + (1 if result else 0)
        out.append(f"{path} · {lines} 行\n", style="bold #e5e7eb")
        out.append("\n".join(result.splitlines()[:5]), style="#94a3b8")
        return out
    if name in ("write_file", "create_file"):
        path = args.get("file_path") or ""
        lines = result.count("\n") + (1 if result else 0)
        out.append(f"{path} · {lines} 行\n", style="bold #e5e7eb")
        out.append("\n".join(result.splitlines()[:10]), style="#94a3b8")
        return out
    if name == "delete_file":
        out.append(f"{args.get('file_path', '')} (已删除)", style="#f87171")
        return out
    if name in ("web", "fetch_url"):
        out.append(f"{args.get('url', '')}\n", style="bold #e5e7eb")
        out.append(result[:1000], style="#94a3b8")
        return out
    if name.startswith("git_") or name in ("lint", "test", "run_lint", "run_tests"):
        out.append(result[:1500] or "(no output)", style="#94a3b8")
        return out
    out.append(result or "(no output)", style="#94a3b8")
    return out


class ToolCard(CardBase):
    """A tool invocation: expanded while running, auto-collapsed when done."""

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
        self._body_widget = Static("", classes="tool-body")
        self.add_body(self._body_widget, "")

    # -- lifecycle -----------------------------------------------------

    def start(self, name: str, args: Dict[str, Any]) -> None:
        self._name = name
        self._args = dict(args or {})
        self._status = "running"
        self.set_title(title=name, icon="⟳", meta=_tool_summary(name, self._args))
        self.set_accent(ACCENT_RUNNING)
        self._render_body()
        if self.collapsed:
            self._set_collapsed(False)

    def finish(
        self,
        result: str,
        is_error: bool,
        duration: Optional[float] = None,
    ) -> None:
        self._result = result or ""
        self._duration = duration
        if tool_is_denied(self._result):
            self._status = "denied"
        elif is_error or tool_is_error(self._result):
            self._status = "error"
        else:
            self._status = "done"

        icon = {"done": "✓", "error": "✗", "denied": "⛔"}[self._status]
        accent = {
            "done": ACCENT_DONE,
            "error": ACCENT_ERROR,
            "denied": ACCENT_ERROR,
        }[self._status]
        meta = _tool_summary(self._name, self._args)
        if duration is not None:
            meta = f"{meta} · {duration:.1f}s"
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
        meta = _tool_summary(self._name, self._args)
        self.set_title(meta=f"{meta} · {seconds:.1f}s")

    # -- interaction ---------------------------------------------------

    @property
    def status_icon(self) -> str:
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
        body = render_tool_body(self._name, self._args, self._result)
        lines = body.split("\n")
        if len(lines) > MAX_BODY_LINES:
            body = Text("\n").join(lines[:MAX_BODY_LINES])
            body.append(
                f"\n… (+{len(lines) - MAX_BODY_LINES} 行)",
                style="#64748b",
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
