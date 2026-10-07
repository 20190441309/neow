"""Approval modal and decision mapping (design spec §7.5)."""

from __future__ import annotations

from concurrent.futures import Future
from enum import Enum
from typing import Any, Dict, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


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
        background: #05060a 65%;
        align: center middle;
    }
    .approval-box {
        width: 74;
        height: auto;
        border: round #facc15;
        background: #0f1117;
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

    # -- content -------------------------------------------------------

    def _title_text(self) -> Text:
        out = Text()
        out.append("⚠ 审批请求", style="#facc15 bold")
        segment = self.tool
        if self.tier:
            segment += f" · tier: {self.tier}"
        out.append(f"   {segment}", style="#64748b")
        return out

    def _detail_text(self) -> Text:
        summary = str(self.params)
        if len(summary) > 200:
            summary = summary[:200] + "…"
        out = Text()
        out.append("$ ", style="#64748b")
        out.append(summary, style="#e5e7eb")
        out.append("\n\n原因：", style="#94a3b8")
        out.append(self.reason, style="#71717a")
        return out

    @staticmethod
    def _hint_text() -> Text:
        return Text.assemble(
            ("[y]", "#34d399 bold"),
            (" 允许一次    ", "#94a3b8"),
            ("[a]", "#22d3ee bold"),
            (" 本会话总是允许    ", "#94a3b8"),
            ("[n/Esc]", "#f87171 bold"),
            (" 拒绝", "#94a3b8"),
        )

    # -- actions -------------------------------------------------------

    def action_allow_once(self) -> None:
        self.dismiss(ApprovalDecision.ALLOW_ONCE)

    def action_allow_always(self) -> None:
        self.dismiss(ApprovalDecision.ALLOW_ALWAYS)

    def action_deny(self) -> None:
        self.dismiss(ApprovalDecision.DENY)


__all__ = ["ApprovalDecision", "ApprovalModal", "apply_decision"]
