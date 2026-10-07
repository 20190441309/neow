"""Chat screen: turn lifecycle, cards, queueing and approval wiring."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from textual import work
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Static

from neow.tui.bridge.controller import ChatController
from neow.tui.bridge.events import (
    ContentDelta,
    ReasoningDelta,
    ReasoningEnd,
    ReasoningStarted,
    ToolFinished,
    ToolStarted,
    TurnCompleted,
    TurnFailed,
)
from neow.tui.widgets.cards import (
    AssistantCard,
    CardBase,
    ErrorCard,
    SystemCard,
    ThinkingCard,
    ToolCard,
    UserCard,
)
from neow.tui.widgets.status_bar import StatusBar, TopBar
from neow.tui.widgets.timeline import TimelineScroll

SIDEBAR_TABS = ("context", "tree", "git")


class TuiEventMessage(Message):
    """Worker-thread -> UI-thread wrapper for controller events."""

    def __init__(self, event: Any):
        self.event = event
        super().__init__()


class ChatScreen(Screen):
    """Main screen: top bar, timeline, sidebar, input dock, status bar."""

    BINDINGS = [
        ("escape", "cancel_or_close", "中断"),
        ("ctrl+o", "toggle_card", "折叠"),
        ("ctrl+t", "cycle_sidebar", "侧栏页"),
        ("tab", "toggle_sidebar", "侧栏"),
    ]

    def __init__(self):
        super().__init__()
        self._busy = False
        self._queue: List[str] = []
        self._turn_number = 0
        self._turn_started = 0.0
        self._current_assistant: Optional[AssistantCard] = None
        self._current_thinking: Optional[ThinkingCard] = None
        self._running_tools: Dict[str, ToolCard] = {}
        self._tool_started: Dict[str, float] = {}
        self._controller: Optional[ChatController] = None
        self.sidebar_tab = "context"

    # -- composition ---------------------------------------------------

    def compose(self):
        yield TopBar(id="topbar")
        with Horizontal(id="body"):
            yield TimelineScroll(id="timeline")
            yield Vertical(id="sidebar")
        yield Static(id="queuestrip")
        with Vertical(id="inputdock"):
            yield Static("❯ 输入消息…", id="input-placeholder")
        yield StatusBar(id="statusbar")

    def on_mount(self) -> None:
        self.apply_width_classes(self.size.width)
        app = self.app
        self._controller = ChatController(
            app.conversation,
            event_callback=self._post_event,
            approval_bridge=getattr(app, "approval_bridge", None),
            token_tracker=getattr(app, "token_tracker", None),
            event_bus=getattr(app, "event_bus", None),
        )
        self.refresh_status()

    # -- responsive breakpoints (spec §4.3) ----------------------------

    def on_resize(self, event) -> None:
        self.apply_width_classes(event.size.width)

    def apply_width_classes(self, width: int) -> None:
        self.set_class(width < 110, "small-sidebar")
        self.set_class(width < 88, "no-sidebar")
        self.set_class(width < 72, "narrow")

    # -- widgets -------------------------------------------------------

    @property
    def timeline(self) -> TimelineScroll:
        return self.query_one("#timeline", TimelineScroll)

    @property
    def status_bar(self) -> StatusBar:
        return self.query_one("#statusbar", StatusBar)

    @property
    def sidebar(self) -> Vertical:
        return self.query_one("#sidebar", Vertical)

    @property
    def sidebar_visible(self) -> bool:
        return self.sidebar.has_class("visible")

    # -- public API ----------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def queued(self) -> List[str]:
        return list(self._queue)

    def submit_prompt(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        if self._busy:
            self._queue.append(text)
            self._update_queue_strip()
            return
        self._start_turn(text)

    def cancel_turn(self) -> None:
        if self._controller is not None:
            self._controller.cancel()

    # -- turn lifecycle ------------------------------------------------

    def _start_turn(self, text: str) -> None:
        self._busy = True
        self._turn_number += 1
        self._turn_started = time.monotonic()
        self._current_assistant = None
        self._current_thinking = None
        self._running_tools = {}
        self._tool_started = {}
        self.timeline.add_card(
            UserCard(text, number=self._turn_number, timestamp=self._timestamp())
        )
        self.status_bar.set_activity("✻ thinking")
        self._run_turn(text)

    @work(thread=True, exclusive=True)
    def _run_turn(self, text: str) -> None:
        if self._controller is not None:
            self._controller.run_turn(text)

    def _post_event(self, event: Any) -> None:
        self.post_message(TuiEventMessage(event))

    def on_tui_event_message(self, message: TuiEventMessage) -> None:
        self.handle_event(message.event)

    def handle_event(self, event: Any) -> None:
        if isinstance(event, ReasoningStarted):
            self._ensure_thinking()
        elif isinstance(event, ReasoningDelta):
            self._ensure_thinking().append_reasoning(event.text)
        elif isinstance(event, ReasoningEnd):
            card = self._ensure_thinking()
            card.finish_reasoning(event.duration)
            self._current_thinking = None
        elif isinstance(event, ContentDelta):
            card = self._ensure_assistant()
            self.call_later(card.append_content, event.text)
        elif isinstance(event, ToolStarted):
            self._current_assistant = None
            card = ToolCard(effects=self.app.effects)
            card.start(event.name, event.args)
            self._running_tools[event.name] = card
            self._tool_started[event.name] = time.monotonic()
            self.timeline.add_card(card)
            self.status_bar.set_activity(f"⟳ {event.name}")
        elif isinstance(event, ToolFinished):
            card = self._running_tools.pop(event.name, None)
            started = self._tool_started.pop(event.name, None)
            if card is not None:
                duration = (time.monotonic() - started) if started else None
                card.finish(event.result, event.is_error, duration=duration)
        elif isinstance(event, TurnCompleted):
            self._finish_turn(event.content)
        elif isinstance(event, TurnFailed):
            self.timeline.add_card(ErrorCard("模型错误", event.message))
            self._finish_turn("")

    def _ensure_thinking(self) -> ThinkingCard:
        if self._current_thinking is None:
            card = ThinkingCard(effects=self.app.effects)
            self._current_thinking = card
            self.timeline.add_card(card)
        return self._current_thinking

    def _ensure_assistant(self) -> AssistantCard:
        if self._current_assistant is None:
            card = AssistantCard(
                number=self._turn_number, timestamp=self._timestamp()
            )
            self._current_assistant = card
            self.timeline.add_card(card)
        return self._current_assistant

    def _finish_turn(self, content: str) -> None:
        duration = time.monotonic() - self._turn_started
        if self._current_assistant is not None:
            self._current_assistant.finish(duration)
            self._current_assistant = None
        if self._current_thinking is not None:
            self._current_thinking.finish_reasoning(duration)
            self._current_thinking = None
        self._busy = False
        self.status_bar.set_activity("idle")
        self.refresh_status()

        if self._queue:
            nxt = self._queue.pop(0)
            self._update_queue_strip()
            self._start_turn(nxt)
            return

        feedback = getattr(self.app.conversation, "pending_lint_feedback", None)
        if feedback:
            self.app.conversation.pending_lint_feedback = None
            self.timeline.add_card(
                SystemCard("自动修复 lint/test 错误", level="warn")
            )
            self._start_turn(feedback)

    # -- status / queue ------------------------------------------------

    def refresh_status(self) -> None:
        tracker = getattr(self.app, "token_tracker", None)
        if tracker is None:
            return
        try:
            self.status_bar.set_tokens(
                getattr(tracker, "session_input", 0),
                getattr(tracker, "session_output", 0),
                tracker.get_session_cost(),
            )
        except Exception:
            pass

    def _update_queue_strip(self) -> None:
        strip = self.query_one("#queuestrip", Static)
        if self._queue:
            strip.update(f"⏳ 排队 {len(self._queue)} · ↑ 取回")
        strip.set_class(bool(self._queue), "visible")

    @staticmethod
    def _timestamp() -> str:
        return time.strftime("%H:%M")

    # -- actions -------------------------------------------------------

    def action_cancel_or_close(self) -> None:
        if self._busy:
            self.cancel_turn()

    def action_toggle_card(self) -> None:
        focused = self.focused
        if isinstance(focused, CardBase):
            focused.toggle()
            return
        cards = self.timeline.cards()
        if cards:
            cards[-1].toggle()

    def action_toggle_sidebar(self) -> None:
        sidebar = self.sidebar
        visible = sidebar.has_class("visible")
        if not visible and self.has_class("no-sidebar"):
            self.notify("终端宽度不足，无法显示侧栏", severity="warning", timeout=2)
            return
        sidebar.set_class(not visible, "visible")

    def action_cycle_sidebar(self) -> None:
        index = SIDEBAR_TABS.index(self.sidebar_tab)
        self.sidebar_tab = SIDEBAR_TABS[(index + 1) % len(SIDEBAR_TABS)]

    def action_quit_app(self) -> None:
        self.app.exit()
