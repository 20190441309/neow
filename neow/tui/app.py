"""Neow full-screen TUI application."""

from __future__ import annotations

from typing import Any, Optional

from textual.app import App

from neow.tui.screens.chat import ChatScreen


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
        self.effects = effects or self._config_effects()

    def _config_effects(self) -> str:
        if self.config is not None:
            try:
                return self.config.tui.get("effects", "full")
            except Exception:
                pass
        return "full"

    def on_mount(self) -> None:
        self.push_screen(ChatScreen())


def run_tui(conversation: Any, **kwargs: Any) -> None:
    """Run the full-screen TUI (blocking)."""

    NeowApp(conversation, **kwargs).run()
