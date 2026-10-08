"""Approval modal and decision mapping (design spec §7.5)."""

from __future__ import annotations

from concurrent.futures import Future
from enum import Enum
from typing import Any, Dict

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import RadioButton, RadioSet, Static

from neow.tui.theme import get_palette


def _clip(text: str, limit: int = 400) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


class ApprovalDecision(Enum):
    ALLOW_ONCE = "allow_once"
    ALLOW_ALWAYS = "allow_always"
    DENY = "deny"


def apply_decision(
    decision: ApprovalDecision,
    policy: Any,
    tool: str,
    future: Future,
) -> bool:
    """Resolve a modal decision into a policy override and a Future result."""

    approved = decision in (
        ApprovalDecision.ALLOW_ONCE,
        ApprovalDecision.ALLOW_ALWAYS,
    )
    if decision is ApprovalDecision.ALLOW_ALWAYS and policy is not None:
        try:
            policy.set_tool_override(tool, "allow")
        except Exception:
            pass
    if not future.done():
        future.set_result(approved)
    return approved


class ApprovalModal(ModalScreen[ApprovalDecision]):
    """Modal shown when the executor requests approval."""

    DEFAULT_CSS = """
    ApprovalModal {
        background: $background 65%;
        align: center middle;
    }
    .approval-box {
        width: 76;
        max-width: 94%;
        max-height: 90%;
        height: auto;
        border: round $warning;
        background: $surface;
        padding: 1 2;
    }
    .approval-title {
        padding: 0 0 1 0;
    }
    .approval-command {
        padding: 0 1;
    }
    .approval-reason {
        padding: 1 0 0 0;
    }
    .approval-hint {
        padding: 1 0 0 0;
    }
    """

    BINDINGS = [
        Binding("y", "allow_once", "允许一次"),
        Binding("a", "allow_always", "总是允许"),
        Binding("n", "deny", "拒绝"),
        Binding("escape", "deny", "拒绝", show=False),
    ]

    def __init__(
        self,
        *,
        tool: str,
        params: Dict[str, Any],
        reason: str,
        tier: str = "",
    ):
        super().__init__()
        self.tool = tool
        self.params = params or {}
        self.reason = reason
        self.tier = tier

    def compose(self) -> ComposeResult:
        box = VerticalScroll(classes="approval-box")
        box.border_title = "⚠ 审批请求"
        with box:
            yield Static(self._title_text(), classes="approval-title")
            yield Static(self._detail_text(), classes="approval-command")
            if self.reason:
                yield Static(self._reason_text(), classes="approval-reason")
            yield Static(self._hint_text(), classes="approval-hint")

    def on_mount(self) -> None:
        self.query_one(VerticalScroll).focus()

    # -- content -------------------------------------------------------

    def _title_text(self) -> Text:
        palette = get_palette(self.app)
        out = Text()
        out.append("neow 想要运行 ", palette["dim"])
        out.append(self.tool, f"bold {palette['text']}")
        if self.tier:
            out.append(f"  · {self.tier}", palette["muted"])
        return out

    def _detail_text(self) -> Text:
        palette = get_palette(self.app)
        out = Text()
        command = self.params.get("command")
        if isinstance(command, str) and len(self.params) == 1:
            out.append("$ ", f"bold {palette['warn']}")
            out.append(_clip(command), f"bold {palette['text']}")
            return out
        for index, (key, value) in enumerate(self.params.items()):
            if index:
                out.append("\n")
            out.append(f"{key}  ", palette["muted"])
            out.append(_clip(str(value)), palette["text"])
        if not self.params:
            out.append("(no parameters)", palette["muted"])
        return out

    def _reason_text(self) -> Text:
        palette = get_palette(self.app)
        return Text.assemble(
            ("原因  ", palette["muted"]),
            (self.reason, palette["dim"]),
        )

    def _hint_text(self) -> Text:
        palette = get_palette(self.app)
        on = palette["surface"]
        return Text.assemble(
            (" y ", f"bold {on} on {palette['success']}"),
            (" 允许一次     ", palette["dim"]),
            (" a ", f"bold {on} on {palette['accent1']}"),
            (" 本会话总是允许     ", palette["dim"]),
            (" n ", f"bold {on} on {palette['error']}"),
            (" 拒绝", palette["dim"]),
            ("  (esc)", palette["muted"]),
        )

    # -- actions -------------------------------------------------------

    def action_allow_once(self) -> None:
        self.dismiss(ApprovalDecision.ALLOW_ONCE)

    def action_allow_always(self) -> None:
        self.dismiss(ApprovalDecision.ALLOW_ALWAYS)

    def action_deny(self) -> None:
        self.dismiss(ApprovalDecision.DENY)


__all__ = ["ApprovalDecision", "ApprovalModal", "ApprovalPicker", "apply_decision"]


class ApprovalPicker(ModalScreen):
    """Pick an approval mode; changes apply immediately."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]

    def __init__(self, *, policy: Any, on_change=None):
        super().__init__()
        self.policy = policy
        self.on_change = on_change

    def compose(self) -> ComposeResult:
        box = Vertical(classes="dialog")
        box.border_title = "审批模式"
        box.border_subtitle = "选择后立即生效 · esc 返回"
        with box:
            yield RadioSet("always-ask", "write", "yolo", id="approval-modes")

    def on_mount(self) -> None:
        order = {"always-ask": 0, "write": 1, "yolo": 2}
        buttons = list(self.query(RadioButton))
        index = order.get(getattr(self.policy.mode, "value", "write"), 1)
        if 0 <= index < len(buttons):
            buttons[index].value = True

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        label = getattr(event.pressed, "label", "")
        text = str(getattr(label, "plain", label)).strip()
        try:
            from neow.core.approval import ApprovalMode

            mode = ApprovalMode(text)
        except ValueError:
            return
        self.policy.set_mode(mode)
        if self.on_change is not None:
            self.on_change(mode)
