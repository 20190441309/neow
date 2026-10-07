"""TUI test helpers (minimal set; extended in plan task 9)."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

from textual.app import App

from neow.tui.app import NeowApp


class FakeConversation:
    """Minimal conversation stand-in for widget/app tests."""

    def __init__(self, script=None, **attrs):
        self.script = list(script or [])
        self.messages = []
        self.model_client = SimpleNamespace(model="fake")
        self.pending_lint_feedback = None
        self.web_cache = {}
        for key, value in attrs.items():
            setattr(self, key, value)


def _chat_app(conversation=None, *, effects=None, config=None, **kwargs):
    """Build a NeowApp for Pilot tests."""

    return NeowApp(
        conversation if conversation is not None else FakeConversation(),
        config=config,
        effects=effects,
        **kwargs,
    )


@asynccontextmanager
async def _host(widget):
    """Mount a single widget in a throwaway App for Pilot tests."""

    class HostApp(App):
        def compose(self):
            yield widget

    app = HostApp()
    async with app.run_test() as pilot:
        yield pilot
