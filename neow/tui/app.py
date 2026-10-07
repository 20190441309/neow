"""Neow full-screen TUI application."""

from __future__ import annotations

import os
from concurrent.futures import Future
from typing import Any, Optional

from textual.app import App, SystemCommand
from textual.theme import Theme

from neow.tui.bridge.controller import ApprovalBridge
from neow.tui.screens.approval import ApprovalModal, apply_decision
from neow.tui.screens.chat import ChatScreen
from neow.tui.theme import PALETTES, theme_variables
from neow.tui.widgets.input_dock import SLASH_COMMANDS
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
    BINDINGS = [("ctrl+q", "quit", "Quit"), ("ctrl+p", "command_palette", "命令面板")]

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
        self.theme_name = self._config_theme()
        self.palette = PALETTES.get(self.theme_name, PALETTES["midnight"])
        self._install_themes()
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

    def _config_theme(self) -> str:
        if self.config is not None:
            try:
                return self.config.tui.get("theme", "midnight")
            except Exception:
                pass
        return "midnight"

    def _install_themes(self) -> None:
        """Register the neow palettes as Textual themes (spec §8.3)."""

        for name, palette in PALETTES.items():
            self.register_theme(
                Theme(
                    name=f"neow-{name}",
                    primary=palette["accent1"],
                    secondary=palette["accent2"],
                    warning=palette["warn"],
                    error=palette["error"],
                    success=palette["success"],
                    accent=palette["accent3"],
                    foreground=palette["text"],
                    background=palette["bg"],
                    surface=palette["surface"],
                    panel=palette["panel"],
                    dark=(name == "midnight"),
                    variables=theme_variables(palette),
                )
            )
        self.theme = f"neow-{self.theme_name}"

    # -- command palette -----------------------------------------------

    def get_system_commands(self, screen):
        """Expose slash commands in the Ctrl+P command palette (spec §7.3)."""

        yield from super().get_system_commands(screen)
        for name in SLASH_COMMANDS:
            yield SystemCommand(name, f"运行 {name}", self._slash_callback(name))

    def _slash_callback(self, name: str):
        def run() -> None:
            dispatch = getattr(self.screen, "dispatch_command", None)
            if callable(dispatch):
                dispatch(name)

        return run

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
