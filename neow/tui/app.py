"""Neow full-screen TUI application."""

from __future__ import annotations

import os
from concurrent.futures import Future
from typing import Any, Optional

from textual.app import App

from neow.tui.bridge.controller import ApprovalBridge
from neow.tui.screens.approval import ApprovalModal, apply_decision
from neow.tui.screens.chat import ChatScreen
from neow.tui.widgets.logo import NeowLogo

VALID_EFFECTS = ("full", "subtle", "off")


def resolve_effects(config_value: str, *, env_none: Optional[bool] = None) -> str:
    """Resolve the effective animation mode (design spec §6.4).

    ``TEXTUAL_ANIMATIONS=none`` forces ``off``.  Non-TTY downgrades are
    enforced earlier by the entry-mode selection (``select_run_mode``).
    """

    animations_off = (
        env_none
        if env_none is not None
        else os.environ.get("TEXTUAL_ANIMATIONS", "").strip().lower() == "none"
    )
    if animations_off:
        return "off"
    return config_value if config_value in VALID_EFFECTS else "full"


class NeowApp(App):
    """Textual application hosting the neow chat screen."""

    CSS_PATH = "theme.tcss"
    TITLE = "neow"
    BINDINGS = [("ctrl+q", "quit", "Quit")]

    def __init__(
        self,
        conversation: Any,
        *,
        config: Any = None,
        token_tracker: Any = None,
        session_manager: Any = None,
        approval_policy: Any = None,
        event_bus: Any = None,
        plugin_api: Any = None,
        executor: Any = None,
        effects: Optional[str] = None,
    ):
        super().__init__()
        self.conversation = conversation
        self.config = config
        self.token_tracker = token_tracker
        self.session_manager = session_manager
        self.approval_policy = approval_policy
        self.event_bus = event_bus
        self.plugin_api = plugin_api
        self.executor = executor
        self.effects = resolve_effects(effects or self._config_effects())
        self.approval_bridge = ApprovalBridge(request=self._request_approval)
        if executor is not None:
            executor.approval_callback = self.approval_bridge

    def _config_effects(self) -> str:
        if self.config is not None:
            try:
                return self.config.tui.get("effects", "full")
            except Exception:
                pass
        return "full"

    # -- splash ---------------------------------------------------------

    def collapse_splash(self) -> None:
        """Collapse the startup logo animation (idempotent)."""

        try:
            logo = self.screen.query_one(NeowLogo)
        except Exception:
            return
        logo.collapse_splash()

    # -- approval bridge -----------------------------------------------

    def _request_approval(
        self,
        tool: str,
        params: dict,
        reason: str,
        future: Future,
    ) -> None:
        """Called on the worker thread; schedules the modal on the UI thread."""

        self.call_from_thread(self._show_approval, tool, params, reason, future)

    def _show_approval(
        self,
        tool: str,
        params: dict,
        reason: str,
        future: Future,
    ) -> None:
        def _done(decision) -> None:
            apply_decision(decision, self.approval_policy, tool, future)

        self.push_screen(
            ApprovalModal(tool=tool, params=params, reason=reason),
            _done,
        )

    # -- lifecycle -----------------------------------------------------

    def on_mount(self) -> None:
        self.push_screen(ChatScreen())


def run_tui(conversation: Any, **kwargs: Any) -> None:
    """Run the full-screen TUI (blocking)."""

    NeowApp(conversation, **kwargs).run()
