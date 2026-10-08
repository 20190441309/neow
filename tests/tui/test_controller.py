"""ChatController tests (plan task 9)."""

from types import SimpleNamespace

from neow.tui.bridge.controller import ChatController
from neow.tui.bridge.events import ContentDelta, TurnCompleted, TurnFailed
from tests.tui.conftest import Chunk, FakeConversation


def _names(events):
    return [type(event).__name__ for event in events]


def test_event_sequence_from_fake_stream():
    conv = FakeConversation(
        script=[
            Chunk(progress={"type": "reasoning_start"}),
            Chunk(reasoning_delta="think"),
            Chunk(progress={"type": "reasoning_end"}),
            Chunk(content_delta="hello"),
            Chunk(
                progress={
                    "type": "tool_start",
                    "name": "read_file",
                    "args": {"path": "a.py"},
                }
            ),
            Chunk(progress={"type": "tool_end", "name": "read_file", "result": "ok"}),
            Chunk(content_delta=" world"),
            Chunk(finish_reason="stop"),
        ]
    )
    events = []
    ctrl = ChatController(conv, event_callback=events.append, time_fn=lambda: 0.0)
    ctrl.run_turn("hi")
    assert _names(events) == [
        "ReasoningStarted",
        "ReasoningDelta",
        "ReasoningEnd",
        "ContentDelta",
        "ToolStarted",
        "ToolFinished",
        "ContentDelta",
        "TurnCompleted",
    ]


def test_delta_coalescing_with_fake_clock():
    now = [0.0]
    conv = FakeConversation(
        script=[
            Chunk(content_delta="a"),
            Chunk(content_delta="b"),
            Chunk(content_delta="c"),
        ]
    )
    events = []
    ctrl = ChatController(
        conv,
        event_callback=events.append,
        flush_interval=0.05,
        time_fn=lambda: now[0],
    )
    now[0] = 0.01
    ctrl.run_turn("hi")
    assert [e.text for e in events if isinstance(e, ContentDelta)] == ["abc"]


def test_cancel_emits_cancelled_turn():
    conv = FakeConversation(
        script=[Chunk(content_delta="a"), "CANCEL", Chunk(content_delta="b")]
    )
    events = []
    ctrl = ChatController(conv, event_callback=events.append, time_fn=lambda: 0.0)
    ctrl.run_turn("hi")
    assert isinstance(events[-1], TurnCompleted) and events[-1].cancelled


def test_cancel_then_new_turn():
    conv = FakeConversation(script=[Chunk(content_delta="a"), "CANCEL"])
    ctrl = ChatController(conv, event_callback=lambda e: None, time_fn=lambda: 0.0)
    ctrl.run_turn("hi")
    ctrl.run_turn("again")
    assert not ctrl.busy


def test_turn_failure_emits_turn_failed():
    conv = FakeConversation(script=RuntimeError("boom"))
    events = []
    ctrl = ChatController(conv, event_callback=events.append, time_fn=lambda: 0.0)
    ctrl.run_turn("hi")
    assert isinstance(events[-1], TurnFailed) and "boom" in events[-1].message


class _Fetcher:
    def __init__(self):
        self.fetched = []

    def fetch(self, url):
        self.fetched.append(url)
        return SimpleNamespace(title="t", text="body")


class _Tracker:
    def __init__(self, maxed=False):
        self.maxed = maxed

    def check_max_tokens(self):
        return self.maxed

    def record(self, usage, model):
        pass


def test_url_autofetch_and_token_limit_parity():
    fetcher = _Fetcher()
    conv = FakeConversation(script=[Chunk(content_delta="ok")])
    ctrl = ChatController(
        conv,
        event_callback=lambda e: None,
        web_fetcher=fetcher,
        time_fn=lambda: 0.0,
    )
    ctrl.run_turn("see https://example.com now")
    assert conv.added_web == ["https://example.com"]

    conv2 = FakeConversation(script=[Chunk(content_delta="x")])
    events = []
    ctrl2 = ChatController(
        conv2,
        event_callback=events.append,
        token_tracker=_Tracker(maxed=True),
        time_fn=lambda: 0.0,
    )
    ctrl2.run_turn("hi")
    assert isinstance(events[-1], TurnFailed)
    assert conv2.stream_consumed is False


def test_controller_passes_cancel_token_and_ids():
    from neow.tui.bridge.events import Notice, ToolFinished, ToolStarted

    conv = FakeConversation(
        script=[
            Chunk(progress={"type": "tool_start", "name": "t", "args": {}, "id": "c1"}),
            Chunk(
                progress={"type": "tool_end", "name": "t", "result": "ok", "id": "c1"}
            ),
            Chunk(progress={"type": "notice", "level": "warn", "message": "limit"}),
        ]
    )
    events = []
    ctrl = ChatController(conv, event_callback=events.append, time_fn=lambda: 0.0)
    ctrl.run_turn("hi")

    started = [e for e in events if isinstance(e, ToolStarted)]
    finished = [e for e in events if isinstance(e, ToolFinished)]
    notices = [e for e in events if isinstance(e, Notice)]
    assert started[0].call_id == finished[0].call_id == "c1"
    assert notices == [Notice(message="limit", level="warn")]

    token = conv.cancel_token
    assert not token.cancelled()
    ctrl.cancel()
    assert token.cancelled()


def test_tool_status_drives_error_and_denied_flags():
    from neow.tui.bridge.events import ToolFinished

    conv = FakeConversation(
        script=[
            Chunk(
                progress={
                    "type": "tool_end",
                    "name": "t",
                    "result": "Error: Security: blocked",
                    "id": "c1",
                    "status": "denied",
                }
            ),
            Chunk(progress={"type": "tool_end", "name": "t", "result": "Error: boom"}),
        ]
    )
    events = []
    ChatController(conv, event_callback=events.append, time_fn=lambda: 0.0).run_turn(
        "hi"
    )
    denied, failed = [e for e in events if isinstance(e, ToolFinished)]
    assert denied.denied and denied.is_error
    assert failed.is_error and not failed.denied
