"""Provider contract tests (plan task 1.1).

Drive each model client with a reference conversation in neow's internal
(OpenAI-style) format and check the request that actually reaches the SDK
against the structural rules of that provider's API.  The SDKs are mocked
only at the network boundary; the conversion code runs for real.
"""

from contextlib import contextmanager
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from neow.core.prompts import get_tool_definitions
from neow.models.anthropic import AnthropicClient
from neow.models.deepseek import DeepSeekClient
from neow.models.openai import OpenAIClient

IMAGE = {
    "type": "image",
    "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgo="},
}


def _call(call_id: str, name: str, arguments: str) -> Dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def _result(call_id: str, content: str) -> Dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": content,
        "type": "tool_result",
    }


# What ConversationManager/AgentLoop actually store.
REFERENCE_CONVERSATION: List[Dict[str, Any]] = [
    {"role": "user", "content": [{"type": "text", "text": "What is in a.py?"}, IMAGE]},
    {
        "role": "assistant",
        "content": "Let me read both files.",
        "tool_calls": [
            _call("call_1", "read_file", '{"file_path": "a.py"}'),
            _call("call_2", "read_file", '{"file_path": "b.py"}'),
        ],
        "reasoning_content": "thinking...",
    },
    _result("call_1", "print('a')"),
    _result("call_2", "Error: file not found"),
    {"role": "assistant", "content": "a.py prints a; b.py is missing."},
    {"role": "user", "content": "Run the tests"},
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [_call("call_3", "execute_command", '{"command": "pytest"}')],
    },
    _result("call_3", "Error: cancelled before execution"),
    # The user typed again after cancelling: two user-side turns in a row.
    {"role": "user", "content": "Never mind, just summarise"},
]


# -- structural validators ------------------------------------------------


def anthropic_problems(kwargs: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    for tool in kwargs.get("tools", []):
        if set(tool) - {"name", "description", "input_schema", "cache_control"}:
            problems.append(f"tool has non-Anthropic keys: {sorted(tool)}")
        if not isinstance(tool.get("input_schema"), dict):
            problems.append(f"tool {tool.get('name')!r} lacks input_schema")
    messages = kwargs["messages"]
    if not messages or messages[0]["role"] != "user":
        problems.append("first message must be from the user")
    previous_tool_uses: List[str] = []
    previous_role = None
    for index, message in enumerate(messages):
        role = message.get("role")
        if set(message) - {"role", "content"}:
            problems.append(f"message {index} has extra keys {sorted(message)}")
        if role not in ("user", "assistant"):
            problems.append(f"message {index} has role {role!r}")
            continue
        if role == previous_role:
            problems.append(f"message {index} repeats role {role!r}")
        previous_role = role
        content = message.get("content")
        blocks = (
            [{"type": "text", "text": content}] if isinstance(content, str) else content
        )
        if not blocks:
            problems.append(f"message {index} is empty")
            continue
        allowed = (
            {"text", "image", "tool_result"} if role == "user" else {"text", "tool_use"}
        )
        results = [b["tool_use_id"] for b in blocks if b.get("type") == "tool_result"]
        if role == "user":
            if sorted(results) != sorted(previous_tool_uses):
                problems.append(
                    f"message {index} answers {results}, expected {previous_tool_uses}"
                )
            leading = [b.get("type") == "tool_result" for b in blocks]
            if results and leading[: len(results)] != [True] * len(results):
                problems.append(f"message {index}: tool_result blocks must come first")
        previous_tool_uses = []
        for block in blocks:
            btype = block.get("type")
            if btype not in allowed:
                problems.append(f"message {index} ({role}) has block {btype!r}")
            if btype == "text" and not block.get("text"):
                problems.append(f"message {index} has an empty text block")
            if btype == "tool_use":
                if not isinstance(block.get("input"), dict):
                    problems.append(
                        f"tool_use {block.get('id')} input is not an object"
                    )
                previous_tool_uses.append(block["id"])
            if btype == "tool_result" and not isinstance(block.get("content"), str):
                problems.append(f"tool_result {block.get('tool_use_id')} content")
    if previous_tool_uses:
        problems.append("conversation ends with unanswered tool_use")
    return problems


OPENAI_KEYS = {
    "system": {"role", "content"},
    "user": {"role", "content", "name"},
    "assistant": {"role", "content", "tool_calls", "name"},
    "tool": {"role", "content", "tool_call_id"},
}


def openai_problems(
    kwargs: Dict[str, Any], extra_keys: Dict[str, set] = None
) -> List[str]:
    extra_keys = extra_keys or {}
    problems: List[str] = []
    for tool in kwargs.get("tools", []):
        if tool.get("type") != "function" or "parameters" not in tool.get(
            "function", {}
        ):
            problems.append(f"tool is not an OpenAI function: {tool}")
    open_calls: List[str] = []
    for index, message in enumerate(kwargs["messages"]):
        role = message.get("role")
        allowed = OPENAI_KEYS.get(role, set()) | extra_keys.get(role, set())
        if role not in OPENAI_KEYS:
            problems.append(f"message {index} has role {role!r}")
        if set(message) - allowed:
            problems.append(
                f"message {index} ({role}) has extra keys {sorted(message)}"
            )
        if role == "tool":
            if message.get("tool_call_id") not in open_calls:
                problems.append(f"message {index} answers an unknown call")
            else:
                open_calls.remove(message["tool_call_id"])
            continue
        if open_calls:
            problems.append(f"calls {open_calls} unanswered before message {index}")
            open_calls = []
        content = message.get("content")
        if isinstance(content, list):
            for part in content:
                if part.get("type") not in ("text", "image_url"):
                    problems.append(f"message {index} has part {part.get('type')!r}")
                if part.get("type") == "image_url" and not part["image_url"][
                    "url"
                ].startswith("data:image/png;base64,"):
                    problems.append(f"message {index} has a malformed image_url")
        for call in message.get("tool_calls") or []:
            if call.get("type") != "function" or not isinstance(
                call["function"].get("arguments"), str
            ):
                problems.append(f"message {index} has a malformed tool call")
            open_calls.append(call["id"])
    return problems


# -- harness --------------------------------------------------------------


def _anthropic_request(stream: bool) -> Dict[str, Any]:
    with patch("neow.models.anthropic.anthropic.Anthropic") as sdk:
        captured: Dict[str, Any] = {}
        response = MagicMock(
            content=[], usage=MagicMock(input_tokens=1, output_tokens=1)
        )

        def create(**kwargs):
            captured.update(kwargs)
            return response

        @contextmanager
        def stream_cm(**kwargs):
            captured.update(kwargs)
            manager = MagicMock()
            manager.__iter__.return_value = iter([])
            manager.get_final_message.return_value = response
            yield manager

        sdk.return_value.messages.create.side_effect = create
        sdk.return_value.messages.stream.side_effect = stream_cm
        client = AnthropicClient(api_key="k")
        args = (REFERENCE_CONVERSATION, "You are neow.", get_tool_definitions())
        if stream:
            list(client.chat_stream(*args))
        else:
            client.chat(*args)
        return captured


def _openai_style_request(module: str, cls, stream: bool) -> Dict[str, Any]:
    with patch(f"neow.models.{module}.openai.OpenAI") as sdk:
        captured: Dict[str, Any] = {}

        def create(**kwargs):
            captured.update(kwargs)
            if kwargs.get("stream"):
                return iter([])
            choice = MagicMock()
            choice.message.content = "ok"
            choice.message.tool_calls = None
            choice.message.reasoning_content = None
            return MagicMock(choices=[choice], usage=None)

        sdk.return_value.chat.completions.create.side_effect = create
        client = cls(api_key="k")
        args = (REFERENCE_CONVERSATION, "You are neow.", get_tool_definitions())
        if stream:
            list(client.chat_stream(*args))
        else:
            client.chat(*args)
        return captured


@pytest.mark.parametrize("stream", [False, True])
def test_anthropic_request_matches_messages_api(stream):
    kwargs = _anthropic_request(stream)
    assert kwargs["system"] == "You are neow."
    assert anthropic_problems(kwargs) == []


@pytest.mark.parametrize("stream", [False, True])
def test_openai_request_matches_chat_completions_api(stream):
    kwargs = _openai_style_request("openai", OpenAIClient, stream)
    assert kwargs["messages"][0] == {"role": "system", "content": "You are neow."}
    assert openai_problems(kwargs) == []


@pytest.mark.parametrize("stream", [False, True])
def test_deepseek_request_matches_chat_completions_api(stream):
    kwargs = _openai_style_request("deepseek", DeepSeekClient, stream)
    # DeepSeek thinking mode needs reasoning_content passed back.
    deepseek_extras = {"assistant": {"reasoning_content"}, "tool": {"type"}}
    assert openai_problems(kwargs, deepseek_extras) == []
    assistant = [m for m in kwargs["messages"] if m["role"] == "assistant"][0]
    assert assistant["reasoning_content"] == "thinking..."


def test_reference_conversation_is_not_mutated():
    snapshot = repr(REFERENCE_CONVERSATION)
    _anthropic_request(stream=False)
    _openai_style_request("openai", OpenAIClient, stream=False)
    assert repr(REFERENCE_CONVERSATION) == snapshot
