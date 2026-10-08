"""Tests for provider message adapters (plan task 1.1)."""

import json
from contextlib import contextmanager
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

from neow.models.adapters import anthropic_tools, to_anthropic, to_openai
from neow.models.anthropic import AnthropicClient

OPENAI_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a file",
        "parameters": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
        },
    },
}


def _assistant_with_calls(*ids):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": cid,
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"file_path": "x"}'},
            }
            for cid in ids
        ],
    }


def test_anthropic_tools_have_input_schema():
    anthropic_native = {
        "name": "t",
        "description": "",
        "input_schema": {"type": "object"},
    }
    assert anthropic_tools([OPENAI_TOOL, anthropic_native]) == [
        {
            "name": "read_file",
            "description": "Read a file",
            "input_schema": OPENAI_TOOL["function"]["parameters"],
        },
        anthropic_native,
    ]


def test_tool_results_merged_into_single_user_message():
    messages, _ = to_anthropic(
        [
            {"role": "user", "content": "go"},
            _assistant_with_calls("a", "b"),
            {
                "role": "tool",
                "tool_call_id": "a",
                "content": "ok",
                "type": "tool_result",
            },
            {"role": "tool", "tool_call_id": "b", "content": "Error: nope"},
            {"role": "user", "content": "thanks"},
        ]
    )
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert messages[1]["content"] == [
        {
            "type": "tool_use",
            "id": "a",
            "name": "read_file",
            "input": {"file_path": "x"},
        },
        {
            "type": "tool_use",
            "id": "b",
            "name": "read_file",
            "input": {"file_path": "x"},
        },
    ]
    assert messages[2]["content"] == [
        {"type": "tool_result", "tool_use_id": "a", "content": "ok"},
        {
            "type": "tool_result",
            "tool_use_id": "b",
            "content": "Error: nope",
            "is_error": True,
        },
        {"type": "text", "text": "thanks"},
    ]


def test_empty_assistant_text_and_empty_results_are_normalised():
    messages, _ = to_anthropic(
        [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": ""},
            {"role": "user", "content": "again"},
            _assistant_with_calls("a"),
            {"role": "tool", "tool_call_id": "a", "content": ""},
        ]
    )
    # The empty assistant turn disappears and the two user turns merge.
    assert messages[0] == {
        "role": "user",
        "content": [{"type": "text", "text": "hi"}, {"type": "text", "text": "again"}],
    }
    assert messages[2]["content"][0]["content"] == "(no output)"


def test_malformed_arguments_become_empty_input():
    call = _assistant_with_calls("a")
    call["tool_calls"][0]["function"]["arguments"] = '{"file_path": '
    messages, _ = to_anthropic([{"role": "user", "content": "x"}, call])
    assert messages[1]["content"][0]["input"] == {}


def test_openai_image_block_converted_and_extra_keys_dropped():
    image = {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAA"},
    }
    source = [
        {"role": "user", "content": [{"type": "text", "text": "see"}, image]},
        {"role": "assistant", "content": "ok", "reasoning_content": "hmm"},
        {"role": "tool", "tool_call_id": "a", "content": "r", "type": "tool_result"},
    ]
    converted = to_openai(source)
    assert converted[0]["content"][1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/jpeg;base64,AAA"},
    }
    assert converted[1] == {"role": "assistant", "content": "ok"}
    assert converted[2] == {"role": "tool", "tool_call_id": "a", "content": "r"}
    assert (
        to_openai(source, extra_keys=("reasoning_content",))[1]["reasoning_content"]
        == "hmm"
    )
    assert source[0]["content"][1] is image  # input untouched


def _start(index, block_id, name):
    return NS(
        type="content_block_start",
        index=index,
        content_block=NS(type="tool_use", id=block_id, name=name),
    )


def _json(index, partial):
    return NS(
        type="content_block_delta",
        index=index,
        delta=NS(type="input_json_delta", partial_json=partial),
    )


def test_anthropic_stream_parallel_tool_inputs():
    events = [
        NS(type="content_block_start", index=0, content_block=NS(type="text")),
        NS(type="content_block_delta", index=0, delta=NS(type="text_delta", text="Hi")),
        _start(1, "toolu_a", "read_file"),
        _json(1, '{"file_path": '),
        _start(2, "toolu_b", "git_status"),  # no arguments: no deltas at all
        _json(1, '"a.py"}'),
        _start(3, "toolu_c", "read_file"),
        _json(3, '{"file_path": "c.py"}'),
        NS(type="message_stop"),
    ]
    with patch("neow.models.anthropic.anthropic.Anthropic") as sdk:

        @contextmanager
        def stream(**kwargs):
            manager = MagicMock()
            manager.__iter__.return_value = iter(events)
            manager.get_final_message.return_value = None
            yield manager

        sdk.return_value.messages.stream.side_effect = stream
        chunks = list(
            AnthropicClient(api_key="k").chat_stream([{"role": "user", "content": "x"}])
        )

    calls = next(c for c in chunks if c.tool_call_delta).tool_call_delta["tool_calls"]
    parsed = {c["id"]: json.loads(c["function"]["arguments"]) for c in calls}
    assert parsed == {
        "toolu_a": {"file_path": "a.py"},
        "toolu_b": {},
        "toolu_c": {"file_path": "c.py"},
    }
