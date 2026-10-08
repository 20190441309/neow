"""Output token limits and truncated replies (plan task 1.2)."""

import json
from contextlib import contextmanager
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import pytest

from neow.core.agent_loop import TRUNCATED_RESULT, validate_history
from neow.core.config import Config, ConfigError
from neow.models.anthropic import AnthropicClient
from neow.models.base import ModelResponse, StreamChunk
from neow.models.factory import create_model_client
from tests.test_agent_loop import RecordingExecutor, _call, _conversation


def _config(tmp_path, entry):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"models": {"m": {"api_key": "k", **entry}}}))
    return Config(path)


def _captured_request(client, sdk_create):
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        choice = MagicMock(finish_reason="stop")
        choice.message.content = "ok"
        choice.message.tool_calls = None
        return MagicMock(
            choices=[choice], usage=None, content=[], stop_reason="end_turn"
        )

    sdk_create.side_effect = create
    client.chat([{"role": "user", "content": "hi"}])
    return captured


@pytest.mark.parametrize(
    "model, expected",
    [
        ("claude-sonnet-4-6", 16000),
        ("claude-3-5-haiku-latest", 8192),
        ("claude-3-haiku-20240307", 4096),
    ],
)
def test_anthropic_default_output_limit(model, expected):
    with patch("neow.models.anthropic.anthropic.Anthropic") as sdk:
        client = AnthropicClient(api_key="k", model=model)
        kwargs = _captured_request(client, sdk.return_value.messages.create)
    assert kwargs["max_tokens"] == expected


def test_max_output_tokens_from_config(tmp_path):
    config = _config(
        tmp_path,
        {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "max_output_tokens": 32000,
        },
    )
    with patch("neow.models.anthropic.anthropic.Anthropic") as sdk:
        client = create_model_client(config, "m")
        kwargs = _captured_request(client, sdk.return_value.messages.create)
    assert client.max_output_tokens == 32000
    assert kwargs["max_tokens"] == 32000


def test_invalid_max_output_tokens_is_rejected(tmp_path):
    config = _config(
        tmp_path,
        {"provider": "deepseek", "model": "deepseek-chat", "max_output_tokens": 0},
    )
    with pytest.raises(ConfigError, match="max_output_tokens"):
        create_model_client(config, "m")


@pytest.mark.parametrize(
    "entry, expected",
    [
        # OpenAI: the API default is the model's own maximum, so send nothing.
        ({"provider": "openai", "model": "gpt-4o"}, {}),
        (
            {"provider": "openai", "model": "gpt-4o", "max_output_tokens": 2000},
            {"max_completion_tokens": 2000},
        ),
        # Compatible endpoints are more likely to know the classic name.
        (
            {
                "provider": "openai-compatible",
                "model": "llama",
                "base_url": "http://localhost:11434/v1",
                "max_output_tokens": 2000,
            },
            {"max_tokens": 2000},
        ),
        # DeepSeek's API default is 4096; raise it to the model maximum.
        ({"provider": "deepseek", "model": "deepseek-chat"}, {"max_tokens": 8192}),
    ],
)
def test_openai_style_output_limit_parameters(tmp_path, entry, expected):
    config = _config(tmp_path, {**entry, "validate": "skip"})
    module = "deepseek" if entry["provider"] == "deepseek" else "openai"
    with patch(f"neow.models.{module}.openai.OpenAI") as sdk:
        client = create_model_client(config, "m")
        kwargs = _captured_request(client, sdk.return_value.chat.completions.create)
    limits = {
        k: v for k, v in kwargs.items() if k in ("max_tokens", "max_completion_tokens")
    }
    assert limits == expected


def test_anthropic_reports_normalised_finish_reasons():
    with patch("neow.models.anthropic.anthropic.Anthropic") as sdk:
        sdk.return_value.messages.create.return_value = MagicMock(
            content=[],
            stop_reason="max_tokens",
            usage=NS(input_tokens=1, output_tokens=1),
        )
        final = MagicMock(
            stop_reason="tool_use", usage=NS(input_tokens=1, output_tokens=2)
        )

        @contextmanager
        def stream(**kwargs):
            manager = MagicMock()
            manager.__iter__.return_value = iter([NS(type="message_stop")])
            manager.get_final_message.return_value = final
            yield manager

        sdk.return_value.messages.stream.side_effect = stream
        client = AnthropicClient(api_key="k")
        assert client.chat([{"role": "user", "content": "x"}]).finish_reason == "length"
        reasons = [c.finish_reason for c in client.chat_stream([]) if c.finish_reason]
    assert reasons == ["tool_calls"]


class _TruncatingClient:
    """First reply is cut off by the output limit; the second is normal."""

    model = "fake"

    def __init__(self, first):
        self.replies = [first, {"content": "Done in smaller steps."}]
        self.requests = 0

    def chat_stream(self, messages, system_prompt=None, tools=None):
        self.requests += 1
        reply = self.replies.pop(0)
        if reply.get("content"):
            yield StreamChunk(content_delta=reply["content"])
        if reply.get("tool_calls"):
            yield StreamChunk(tool_call_delta={"tool_calls": reply["tool_calls"]})
        yield StreamChunk(finish_reason=reply.get("finish_reason", "stop"))

    def chat(self, messages, system_prompt=None, tools=None):
        chunks = list(self.chat_stream(messages, system_prompt, tools))
        calls = [c.tool_call_delta for c in chunks if c.tool_call_delta]
        return ModelResponse(
            content="".join(c.content_delta for c in chunks),
            tool_calls=calls[0]["tool_calls"] if calls else [],
            finish_reason=[c.finish_reason for c in chunks if c.finish_reason][-1],
        )


@pytest.mark.parametrize("stream", [True, False])
def test_length_finish_with_tool_call_returns_error_result(stream):
    cut_off = {
        "content": "Writing the file",
        "tool_calls": [
            {
                "id": "c1",
                "function": {
                    "name": "write_file",
                    "arguments": '{"file_path": "a.py", "con',
                },
            }
        ],
        "finish_reason": "length",
    }
    executor = RecordingExecutor()
    conv, _ = _conversation([], executor)
    conv.model_client = client = _TruncatingClient(cut_off)

    if stream:
        chunks = list(conv.get_response_stream("write a big file"))
    else:
        conv.get_response("write a big file")
        chunks = []

    assert executor.calls == []  # the half-written call never ran
    assert client.requests == 2  # the model was asked to try again
    results = [m["content"] for m in conv.messages if m["role"] == "tool"]
    assert results == [TRUNCATED_RESULT]
    assert conv.messages[-1]["content"] == "Done in smaller steps."
    assert validate_history(conv.messages) == []
    if stream:
        notices = [
            c.progress for c in chunks if c.progress and c.progress["type"] == "notice"
        ]
        assert notices and notices[0]["level"] == "warn"


def test_length_finish_text_emits_warning():
    conv, _ = _conversation([], RecordingExecutor())
    conv.model_client = client = _TruncatingClient(
        {"content": "The answer is long and", "finish_reason": "length"}
    )

    chunks = list(conv.get_response_stream("explain"))

    assert client.requests == 1  # no automatic continuation
    notices = [
        c.progress for c in chunks if c.progress and c.progress["type"] == "notice"
    ]
    assert len(notices) == 1 and "max_output_tokens" in notices[0]["message"]
    assert conv.messages[-1] == {
        "role": "assistant",
        "content": "The answer is long and",
    }


def test_normal_tool_turn_has_no_truncation_notice():
    conv, _ = _conversation(
        [{"content": "", "tool_calls": [_call("c1", "read_file", file_path="a")]}]
    )
    chunks = list(conv.get_response_stream("x"))
    assert not [c for c in chunks if c.progress and c.progress["type"] == "notice"]
