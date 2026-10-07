"""Top bar and status bar widgets."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.text import Text
from textual.containers import Horizontal
from textual.widgets import Static


def _git_branch() -> Optional[str]:
    """Best-effort current git branch; None outside a repo."""

    try:
        from neow.tools.git import _run_git

        branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
        return branch or None
    except Exception:
        return None


class NeowLogo(Static):
    """Neow wordmark (animated splash lands in plan task 15)."""

    def __init__(self, *, effects: str = "full"):
        super().__init__("◆ NEOW", classes="logo")
        self.effects = effects
        self._timer = None

    @property
    def collapsed_splash(self) -> bool:
        """Whether the startup splash has been collapsed to the mark."""

        return True


class TopBar(Horizontal):
    """One-line chrome: logo, model, branch, approval mode, cwd."""

    def compose(self):
        yield NeowLogo(effects=getattr(self.app, "effects", "full"))
        yield Static(id="topbar-info")

    def on_mount(self) -> None:
        self.refresh_info()

    def refresh_info(self) -> None:
        app = self.app
        conversation = getattr(app, "conversation", None)
        model = getattr(getattr(conversation, "model_client", None), "model", "unknown")
        parts: list[tuple[str, str]] = [(f"  {model}", "#a78bfa")]

        branch = _git_branch()
        if branch:
            parts += [("  ·  ", "#334155"), (f"⎇ {branch}", "#94a3b8")]

        policy = getattr(app, "approval_policy", None)
        if policy is not None:
            parts += [("  ·  ", "#334155"), (f"⛨ {policy.mode.value}", "#facc15")]

        parts += [("  ·  ", "#334155"), (str(Path.cwd()), "#64748b")]

        info = Text()
        for segment, style in parts:
            info.append(segment, style)
        self.query_one("#topbar-info", Static).update(info)


class StatusBar(Static):
    """One-line footer: tokens, cost, context, activity."""

    def __init__(self, *args, **kwargs):
        super().__init__("", *args, **kwargs)
        self._input_tokens = 0
        self._output_tokens = 0
        self._cost: Optional[float] = None
        self._context_pct: Optional[float] = None
        self._activity = "idle"

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
        self._activity = text
        self._refresh()

    def _refresh(self) -> None:
        self.update(self._render_text())

    def _render_text(self) -> Text:
        out = Text()
        out.append(f"▲{self._input_tokens} ▼{self._output_tokens}", "#94a3b8")
        if self._cost is not None:
            out.append("  ·  ", "#334155")
            out.append(f"${self._cost:.4f}", "#34d399")
        if self._context_pct is not None:
            out.append("  ·  ", "#334155")
            out.append(f"ctx {self._context_pct:.0f}%", "#94a3b8")
        out.append("        ", "")
        out.append(self._activity, "#a78bfa" if self._activity != "idle" else "#64748b")
        return out
