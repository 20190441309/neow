"""TUI test helpers (minimal set; extended in plan task 9)."""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from textual.app import App

from neow.tui.app import NeowApp


@dataclass
class Chunk:
    """A StreamChunk-compatible item for controller tests."""

    content_delta: str = ""
    reasoning_delta: str = ""
    tool_call_delta: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    progress: Optional[Dict[str, Any]] = None


class FakeConversation:
    """Minimal conversation stand-in for widget/app/controller tests."""

    def __init__(self, script=None, **attrs):
        if script is None:
            self.script: List[Any] = []
        elif isinstance(script, (list, tuple)):
            self.script = list(script)
        else:
            self.script = [script]
        self.messages = []
        self.model_client = SimpleNamespace(model="fake")
        self.pending_lint_feedback = None
        self.web_cache: Dict[str, Any] = {}
        self.stream_consumed = False
        self.on_cancel = None
        self.added_web: List[str] = []
        for key, value in attrs.items():
            setattr(self, key, value)

    def get_response_stream(self, user_input: str):
        self.stream_consumed = True
        for item in self.script:
            if isinstance(item, BaseException):
                raise item
            if item == "CANCEL":
                if self.on_cancel is not None:
                    self.on_cancel()
                continue
            yield item

    def add_web_content(self, url: str, content: Any) -> None:
        self.added_web.append(url)
        self.web_cache[url] = content


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


def _screen_app(screen):
    """Build an App whose only screen is *screen* (pushed on mount)."""

    class ScreenHost(App):
        def on_mount(self):
            self.push_screen(screen)

    return ScreenHost()
