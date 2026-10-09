"""Accurate context usage and auto-compaction (plan task 2.3)."""

import json
from unittest.mock import patch

import pytest

from neow.core.config import Config
from neow.models.base import default_context_window
from neow.models.factory import create_model_client
from tests.test_agent_loop import _conversation

USAGE = {"prompt_tokens": 70_000, "completion_tokens": 2_000, "total_tokens": 72_000}


def _conv(usage=USAGE, window=100_000):
    conv, client = _conversation([{"content": "ok", "usage": usage}])
    client.context_window = window
    return conv, client


def test_context_pct_from_usage():
    conv, _ = _conv()
    list(conv.get_response_stream("hi"))
    assert conv.context_usage() == (72_000, 100_000, 72.0)


def test_context_estimated_without_usage():
    conv, _ = _conv(usage={})
    conv.set_system_prompt("x" * 4_000)
    list(conv.get_response_stream("y" * 4_000))
    tokens, window, pct = conv.context_usage()
    assert 1_900 < tokens < 2_300  # ~4 characters per token
    assert pct == pytest.approx(tokens / window * 100)


def test_compaction_discards_stale_usage():
    conv, client = _conv()
    list(conv.get_response_stream("hi"))
    client.replies = [{"content": "summary"}]
    conv.compact()
    tokens, _, _ = conv.context_usage()
    assert tokens < 1_000  # re-estimated from the short summary


@pytest.mark.parametrize(
    "usage, expected",
    [
        ({"prompt_tokens": 81_000, "completion_tokens": 0}, True),
        ({"prompt_tokens": 50_000, "completion_tokens": 0}, False),
    ],
)
def test_should_auto_compact_uses_real_usage(usage, expected):
    conv, _ = _conv(usage=usage)
    conv.messages.extend(
        [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "ok"}]
        * 2
    )
    list(conv.get_response_stream("hi"))
    assert conv.should_auto_compact() is expected


def test_no_auto_compact_for_a_tiny_history():
    conv, _ = _conv(usage={"prompt_tokens": 99_000, "completion_tokens": 0})
    list(conv.get_response_stream("hi"))
    assert conv.should_auto_compact() is False  # nothing worth summarising


@pytest.mark.parametrize(
    "model, window",
    [
        ("claude-sonnet-4-6", 200_000),
        ("gpt-4o", 128_000),
        ("deepseek-v4-flash", 128_000),
        ("some-local-model", 128_000),
    ],
)
def test_default_context_window(model, window):
    assert default_context_window(model) == window


def test_context_window_from_config(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(
        json.dumps(
            {
                "models": {
                    "m": {
                        "api_key": "k",
                        "provider": "openai",
                        "model": "gpt-4o",
                        "context_window": 32_000,
                    }
                }
            }
        )
    )
    with patch("neow.models.openai.openai.OpenAI"):
        client = create_model_client(Config(path), "m")
    assert client.context_window == 32_000
