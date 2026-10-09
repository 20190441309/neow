"""Stable system prompt, deduplicated context and prompt caching (task 2.2)."""

from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

from neow.core.agent_loop import validate_history
from neow.core.token_tracker import TokenTracker
from neow.models.anthropic import AnthropicClient
from neow.models.base import openai_usage
from tests.test_agent_loop import ScriptedClient, _conversation


class RecordingClient(ScriptedClient):
    """ScriptedClient that also remembers each request's system prompt."""

    def __init__(self, replies):
        super().__init__(replies)
        self.systems = []

    def chat_stream(self, messages, system_prompt=None, tools=None):
        self.systems.append(system_prompt)
        yield from super().chat_stream(messages, system_prompt, tools)


def _conv_with_context(tmp_path, replies=3):
    client = RecordingClient([{"content": f"reply {i}"} for i in range(replies)])
    conv, _ = _conversation([], None)
    conv.model_client = client
    conv.set_system_prompt("You are Neow.")
    ctx = MagicMock()
    ctx.get_project_structure.return_value = {"src": {"main.py": None}}
    ctx.get_relevant_files.side_effect = lambda query: (
        [{"path": "src/main.py", "content": "def main(): pass"}]
        if "main" in query
        else []
    )
    conv.context_manager = ctx
    return conv, client


def _context_messages(messages):
    return [m for m in messages if m.get("neow_context")]


def test_system_prompt_stable_across_turns(tmp_path):
    conv, client = _conv_with_context(tmp_path)
    (tmp_path / "a.py").write_text("A = 1\n")
    list(conv.get_response_stream("hello"))
    conv.add_context_file(str(tmp_path / "a.py"))
    list(conv.get_response_stream("look at main please"))
    list(conv.get_response_stream("thanks"))

    assert len(set(client.systems)) == 1
    assert "You are Neow." in client.systems[0]


def test_project_structure_persists_after_first_turn(tmp_path):
    conv, client = _conv_with_context(tmp_path)
    for text in ("one", "two", "three"):
        list(conv.get_response_stream(text))
    assert all("main.py" in system for system in client.systems)
    conv.context_manager.get_project_structure.assert_called_once()


def test_context_files_attached_to_user_turn_once(tmp_path):
    conv, client = _conv_with_context(tmp_path, replies=4)
    path = tmp_path / "a.py"
    path.write_text("A = 1\n")
    conv.add_context_file(str(path))

    list(conv.get_response_stream("first"))
    list(conv.get_response_stream("second"))
    blocks = _context_messages(conv.messages)
    assert len(blocks) == 1 and "A = 1" in blocks[0]["content"]
    # It sits right before the user's own message.
    index = conv.messages.index(blocks[0])
    assert conv.messages[index + 1]["content"] == "first"

    path.write_text("A = 2\n")
    conv.refresh_context_file(str(path.resolve()))
    list(conv.get_response_stream("third"))
    blocks = _context_messages(conv.messages)
    assert len(blocks) == 2 and "A = 2" in blocks[1]["content"]
    assert validate_history(conv.messages) == []

    # After /clear the model has forgotten everything: send it again.
    conv.clear_history()
    list(conv.get_response_stream("fourth"))
    assert len(_context_messages(conv.messages)) == 1


def test_relevant_files_and_web_content_go_to_the_user_turn(tmp_path):
    from neow.tools.web import WebContent

    conv, client = _conv_with_context(tmp_path)
    conv.add_web_content(
        "https://example.com",
        WebContent(
            url="https://example.com",
            title="Example",
            text="Hello web",
            code_blocks=[("python", "x = 1")],
            content_type="webpage",
        ),
    )
    list(conv.get_response_stream("explain main"))
    block = _context_messages(conv.messages)[0]["content"]
    assert "def main(): pass" in block
    assert "Hello web" in block and "x = 1" in block
    assert "Hello web" not in client.systems[0]


def test_anthropic_cache_control_breakpoints():
    with patch("neow.models.anthropic.anthropic.Anthropic") as sdk:
        sdk.return_value.messages.create.return_value = MagicMock(
            content=[], stop_reason="end_turn", usage=None
        )
        client = AnthropicClient(api_key="k")
        client.chat(
            [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
                {"role": "user", "content": "more"},
            ],
            system_prompt="You are Neow.",
            tools=[
                {"type": "function", "function": {"name": "a", "parameters": {}}},
                {"type": "function", "function": {"name": "b", "parameters": {}}},
            ],
        )
        kwargs = sdk.return_value.messages.create.call_args.kwargs

    ephemeral = {"type": "ephemeral"}
    assert kwargs["system"] == [
        {"type": "text", "text": "You are Neow.", "cache_control": ephemeral}
    ]
    assert "cache_control" not in kwargs["tools"][0]
    assert kwargs["tools"][-1]["cache_control"] == ephemeral
    assert kwargs["messages"][-1]["content"][-1]["cache_control"] == ephemeral
    marked = [
        block
        for message in kwargs["messages"]
        for block in message["content"]
        if "cache_control" in block
    ]
    assert len(marked) == 1  # 3 breakpoints in total, the API allows 4


def test_anthropic_usage_includes_cached_input():
    usage = NS(
        input_tokens=100,
        output_tokens=20,
        cache_read_input_tokens=900,
        cache_creation_input_tokens=50,
    )
    with patch("neow.models.anthropic.anthropic.Anthropic") as sdk:
        sdk.return_value.messages.create.return_value = MagicMock(
            content=[], stop_reason="end_turn", usage=usage
        )
        response = AnthropicClient(api_key="k").chat([{"role": "user", "content": "x"}])
    assert response.usage == {
        "prompt_tokens": 1050,
        "completion_tokens": 20,
        "total_tokens": 1070,
        "cache_read_tokens": 900,
        "cache_write_tokens": 50,
    }


def test_openai_and_deepseek_cached_tokens():
    openai_style = NS(
        prompt_tokens=1000,
        completion_tokens=10,
        total_tokens=1010,
        prompt_tokens_details=NS(cached_tokens=768),
    )
    assert openai_usage(openai_style)["cache_read_tokens"] == 768
    deepseek_style = NS(
        prompt_tokens=1000,
        completion_tokens=10,
        total_tokens=1010,
        prompt_tokens_details=None,
        prompt_cache_hit_tokens=640,
    )
    assert openai_usage(deepseek_style)["cache_read_tokens"] == 640
    plain = NS(prompt_tokens=5, completion_tokens=1, total_tokens=6)
    assert openai_usage(plain) == {
        "prompt_tokens": 5,
        "completion_tokens": 1,
        "total_tokens": 6,
    }


def test_tracker_counts_cached_tokens():
    config = MagicMock()
    config.token = {
        "prices": {
            "claude": {"input": 3.0, "output": 15.0},
            "custom": {
                "input": 1.0,
                "output": 1.0,
                "cache_read": 0.5,
                "cache_write": 2.0,
            },
        }
    }
    tracker = TokenTracker(config)
    tracker.record(
        {
            "prompt_tokens": 1_000_000,
            "completion_tokens": 0,
            "cache_read_tokens": 800_000,
            "cache_write_tokens": 100_000,
        },
        "claude",
    )
    # 100k uncached at $3, 800k read at 0.1x, 100k written at 1.25x
    assert round(tracker.get_session_cost(), 4) == round(0.3 + 0.24 + 0.375, 4)
    assert tracker.session_cache_read == 800_000
    assert "80%" in tracker.get_session_summary()

    tracker.record(
        {
            "prompt_tokens": 1_000_000,
            "completion_tokens": 0,
            "cache_read_tokens": 1_000_000,
        },
        "custom",
    )
    assert round(tracker.get_cost_for_model("custom"), 4) == 0.5
