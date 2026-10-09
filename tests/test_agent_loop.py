"""Tests for the unified agent loop (plan task 0.2)."""

import json
from typing import Any, Dict, List

import pytest

from neow.core.agent_loop import CancelToken, repair_history, validate_history
from neow.core.conversation import ConversationManager
from neow.models.base import ModelResponse, StreamChunk


def _call(call_id: str, name: str, **args: Any) -> Dict[str, Any]:
    return {"id": call_id, "function": {"name": name, "arguments": json.dumps(args)}}


class ScriptedClient:
    """Model client replaying one scripted reply per request, in both modes."""

    model = "scripted"

    def __init__(self, replies: List[Dict[str, Any]]):
        self.replies = list(replies)
        self.requests: List[List[Dict[str, Any]]] = []

    def _next(self, messages):
        self.requests.append([dict(m) for m in messages])
        return self.replies.pop(0) if self.replies else {"content": "done"}

    def chat(self, messages, system_prompt=None, tools=None):
        reply = self._next(messages)
        return ModelResponse(
            content=reply.get("content", ""),
            tool_calls=reply.get("tool_calls", []),
            usage=reply.get("usage", {}),
        )

    def chat_stream(self, messages, system_prompt=None, tools=None):
        reply = self._next(messages)
        for piece in reply.get("content_pieces", [reply.get("content", "")]):
            if piece:
                yield StreamChunk(content_delta=piece)
        if reply.get("tool_calls"):
            yield StreamChunk(tool_call_delta={"tool_calls": reply["tool_calls"]})
        if reply.get("usage"):
            yield StreamChunk(usage=reply["usage"])


class RecordingExecutor:
    def __init__(self, on_execute=None, fail=()):
        self.calls: List[tuple] = []
        self.on_execute = on_execute
        self.fail = set(fail)

    def execute(self, name, args):
        self.calls.append((name, args))
        if self.on_execute:
            self.on_execute(name, args)
        if name in self.fail:
            raise RuntimeError(f"{name} exploded")
        return f"{name} ok"


TWO_TOOL_SCRIPT = [
    {
        "content": "Let me look.",
        "tool_calls": [
            _call("c1", "read_file", file_path="a.py"),
            _call("c2", "read_file", file_path="b.py"),
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    },
    {
        "content": "Both files are fine.",
        "usage": {"prompt_tokens": 30, "completion_tokens": 5, "total_tokens": 35},
    },
]


def _conversation(script, executor=None, **kwargs):
    client = ScriptedClient(script)
    conv = ConversationManager(client, tool_executor=executor or RecordingExecutor())
    for key, value in kwargs.items():
        setattr(conv, key, value)
    return conv, client


def test_loop_single_implementation_parity():
    streamed, _ = _conversation(TWO_TOOL_SCRIPT)
    list(streamed.get_response_stream("check files"))
    blocking, _ = _conversation(TWO_TOOL_SCRIPT)
    response = blocking.get_response("check files")

    assert streamed.messages == blocking.messages
    assert response.content == "Both files are fine."
    assert validate_history(streamed.messages) == []
    assert [m["role"] for m in streamed.messages] == [
        "user",
        "assistant",
        "tool",
        "tool",
        "assistant",
    ]


def test_tool_events_carry_call_ids():
    conv, _ = _conversation(TWO_TOOL_SCRIPT)
    progress = [c.progress for c in conv.get_response_stream("x") if c.progress]
    tool_events = [p for p in progress if p["type"].startswith("tool_")]
    assert [(p["type"], p["id"]) for p in tool_events] == [
        ("tool_start", "c1"),
        ("tool_end", "c1"),
        ("tool_start", "c2"),
        ("tool_end", "c2"),
    ]


def test_tool_exception_becomes_error_result():
    conv, _ = _conversation(TWO_TOOL_SCRIPT, RecordingExecutor(fail={"read_file"}))
    conv.get_response("x")
    results = [m["content"] for m in conv.messages if m["role"] == "tool"]
    assert results == ["Error: read_file exploded"] * 2


def test_cancel_mid_tools_repairs_history():
    token = CancelToken()
    executor = RecordingExecutor(on_execute=lambda name, args: token.cancel())
    conv, client = _conversation(TWO_TOOL_SCRIPT, executor)

    list(conv.get_response_stream("x", cancel=token))

    assert len(executor.calls) == 1  # second tool never ran
    assert len(client.requests) == 1  # no follow-up request
    assert validate_history(conv.messages) == []
    results = [m["content"] for m in conv.messages if m["role"] == "tool"]
    assert results[0] == "read_file ok"
    assert "cancelled" in results[1].lower()


def test_generator_close_repairs_history():
    conv, _ = _conversation(TWO_TOOL_SCRIPT)
    stream = conv.get_response_stream("x")
    for chunk in stream:
        if chunk.progress and chunk.progress["type"] == "tool_start":
            stream.close()  # what the TUI does on Esc
            break

    assert validate_history(conv.messages) == []
    assert all(
        "cancelled" in m["content"].lower()
        for m in conv.messages
        if m["role"] == "tool"
    )


def test_cancel_during_content_keeps_partial_answer():
    script = [{"content_pieces": ["Partial ", "answer ", "never finished"]}]
    conv, _ = _conversation(script)
    stream = conv.get_response_stream("x")
    next(stream)
    next(stream)
    stream.close()

    assert conv.messages[-1] == {"role": "assistant", "content": "Partial answer "}


def test_max_turns_stops_loop():
    looping = [
        {"content": "", "tool_calls": [_call(f"c{i}", "read_file", file_path="a")]}
        for i in range(10)
    ]
    conv, client = _conversation(looping, max_turns=3)
    chunks = list(conv.get_response_stream("x"))

    assert len(client.requests) == 3
    notices = [
        c.progress for c in chunks if c.progress and c.progress["type"] == "notice"
    ]
    assert notices and "3" in notices[0]["message"]
    assert validate_history(conv.messages) == []


def test_usage_recorded_for_every_request():
    class Tracker:
        def __init__(self):
            self.records = []

        def record(self, usage, model):
            self.records.append(usage["total_tokens"])

    tracker = Tracker()
    conv, _ = _conversation(TWO_TOOL_SCRIPT, token_tracker=tracker)
    conv.get_response("x")
    assert tracker.records == [12, 35]


def test_validate_and_repair_history():
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "a",
                    "type": "function",
                    "function": {"name": "t", "arguments": "{}"},
                },
                {
                    "id": "b",
                    "type": "function",
                    "function": {"name": "t", "arguments": "{}"},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "a", "content": "ok"},
        {"role": "user", "content": "next"},
    ]
    assert validate_history(messages) == ["tool call 'b' has no result"]

    assert repair_history(messages, "Error: cancelled") == 1
    assert validate_history(messages) == []
    # The synthetic result sits with the other results, before the next user turn.
    assert [m.get("tool_call_id") for m in messages[2:4]] == ["a", "b"]
    assert messages[4]["content"] == "next"


@pytest.mark.parametrize(
    "messages",
    [
        [{"role": "tool", "tool_call_id": "zz", "content": "orphan"}],
    ],
)
def test_validate_history_flags_orphan_results(messages):
    assert validate_history(messages) == ["tool result 'zz' has no matching call"]


def test_agent_config_max_turns(tmp_path):
    from neow.core.config import Config

    default = tmp_path / "default.json"
    default.write_text("{}")
    assert Config(default).agent["max_turns"] == 50

    custom = tmp_path / "custom.json"
    custom.write_text(json.dumps({"agent": {"max_turns": 7}}))
    assert Config(custom).agent["max_turns"] == 7

    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"agent": {"max_turns": 0}}))
    assert Config(invalid).agent["max_turns"] == 50
