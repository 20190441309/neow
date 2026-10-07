"""Approval modal and decision mapping (design spec §7.5)."""

from __future__ import annotations

from concurrent.futures import Future
from enum import Enum
from typing import Any, Dict

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import RadioButton, RadioSet, Static

from neow.tui.theme import get_palette


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
        width: 74;
        height: auto;
        border: round $warning;
        background: $surface;
        padding: 1 2;
    }
    .approval-title {
        padding: 0 0 1 0;
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
        with Vertical(classes="approval-box"):
            yield Static(self._title_text(), classes="approval-title")
            yield Static(self._detail_text())
            yield Static(self._hint_text(), classes="approval-hint")

    def on_mount(self) -> None:
        self._pulse_on = False
        self._pulse_timer = self.set_interval(0.4, self._pulse)

    def _pulse(self) -> None:
        self._pulse_on = not self._pulse_on
        palette = get_palette(self.app)
        try:
            box = self.query_one(".approval-box")
            box.styles.border = (
                "round",
                palette["warn"] if self._pulse_on else palette["muted"],
            )
        except Exception:
            pass

    # -- content -------------------------------------------------------

    def _title_text(self) -> Text:
        palette = get_palette(self.app)
        out = Text()
        out.append("⚠ 审批请求", style=f"{palette['warn']} bold")
        segment = self.tool
        if self.tier:
            segment += f" · tier: {self.tier}"
        out.append(f"   {segment}", style=palette["muted"])
        return out

    def _detail_text(self) -> Text:
        palette = get_palette(self.app)
        summary = str(self.params)
        if len(summary) > 200:
            summary = summary[:200] + "…"
        out = Text()
        out.append("$ ", style=palette["muted"])
        out.append(summary, style=palette["text"])
        out.append("\n\n原因：", style=palette["dim"])
        out.append(self.reason, style=palette["settled"])
        return out

    def _hint_text(self) -> Text:
        palette = get_palette(self.app)
        return Text.assemble(
            ("[y]", f"{palette['success']} bold"),
            (" 允许一次    ", palette["dim"]),
            ("[a]", f"{palette['accent1']} bold"),
            (" 本会话总是允许    ", palette["dim"]),
            ("[n/Esc]", f"{palette['error']} bold"),
            (" 拒绝", palette["dim"]),
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

    BINDINGS = [("escape", "app.pop_screen", "返回")]

    def __init__(self, *, policy: Any, on_change=None):
        super().__init__()
        self.policy = policy
        self.on_change = on_change

    def compose(self) -> ComposeResult:
        yield Static("审批模式 · 选择后立即生效", classes="picker-title")
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
