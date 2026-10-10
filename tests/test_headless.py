"""Headless mode: -p / --output-format text|json|stream-json (plan task 6.1)."""

import json
import os
import time

import pytest
from click.testing import CliRunner

from neow.cli import main as cli
from neow.cli.headless import filter_tools, parse_tool_list
from neow.core.tools_registry import ToolRegistry, ToolSpec
from neow.utils import formatter
from tests.test_agent_loop import ScriptedClient, _call

USAGE = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}


class FakeClient(ScriptedClient):
    model = "fake-model"

    def validate_connection(self):
        return True


class FailingClient(FakeClient):
    def chat_stream(self, messages, system_prompt=None, tools=None):
        raise RuntimeError("upstream 500")
        yield  # pragma: no cover


@pytest.fixture
def run(tmp_path, monkeypatch):
    """Invoke the CLI in a scratch HOME / cwd with a scripted model."""
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(work)
    monkeypatch.setattr("neow.core.checkpoints.ROOT", home / "checkpoints")
    # main() points the console at stderr; restore the unset (dynamic) value.
    monkeypatch.setattr(formatter.console, "_file", formatter.console._file)

    def invoke(args, replies=(), client_cls=FakeClient):
        client = client_cls(list(replies))
        monkeypatch.setattr(cli, "create_model_client", lambda cfg, name: client)
        result = CliRunner().invoke(cli.main, args, catch_exceptions=False)
        return result, client

    return invoke, work


def _lines(output):
    return [json.loads(line) for line in output.splitlines() if line.strip()]


def test_headless_json_schema(run):
    invoke, _ = run
    result, client = invoke(
        ["-p", "hello", "--output-format", "json"],
        [{"content": "Hi there.", "usage": USAGE}],
    )
    assert result.exit_code == 0
    (payload,) = _lines(result.stdout)  # stdout holds exactly one JSON object
    assert payload["type"] == "result"
    assert payload["result"] == "Hi there." and payload["is_error"] is False
    assert payload["num_turns"] == 1 and payload["model"] == "fake-model"
    assert payload["usage"]["input_tokens"] == 120
    assert payload["usage"]["output_tokens"] == 30
    assert isinstance(payload["cost"], float) and payload["duration_ms"] >= 0
    assert payload["session_id"].startswith("session_")
    sessions = os.listdir(os.path.join(os.environ["HOME"], ".neow", "sessions"))
    assert f"{payload['session_id']}.json" in sessions

    # Plain text keeps stdout to the reply alone.
    result, _ = invoke(["-p", "hello"], [{"content": "Just text."}])
    assert result.exit_code == 0 and result.stdout == "Just text.\n"


def test_stream_json_events_order(run):
    invoke, work = run
    (work / "notes.txt").write_text("remember the milk\n")
    result, _ = invoke(
        ["-p", "read notes", "--output-format", "stream-json"],
        [
            {
                "content": "Reading.",
                "tool_calls": [_call("t1", "read_file", file_path="notes.txt")],
            },
            {"content": "It says: remember the milk.", "usage": USAGE},
        ],
    )
    assert result.exit_code == 0
    events = _lines(result.stdout)
    types = [e["type"] for e in events]
    assert types[0] == "init" and types[-1] == "result"
    assert "read_file" in events[0]["tools"]
    assert types.index("tool_start") < types.index("tool_end")
    assert types.index("tool_end") < len(types) - 1
    start = next(e for e in events if e["type"] == "tool_start")
    end = next(e for e in events if e["type"] == "tool_end")
    assert start["name"] == "read_file" and start["id"] == end["id"] == "t1"
    assert end["status"] == "ok" and "remember the milk" in end["result"]
    text = "".join(e["text"] for e in events if e["type"] == "content_delta")
    assert text == "Reading.It says: remember the milk."
    assert events[-1]["num_turns"] == 2


def test_allowed_tools_filter(run):
    invoke, _ = run
    result, client = invoke(
        [
            "-p",
            "x",
            "--output-format",
            "stream-json",
            "--allowed-tools",
            "read_file, grep glob",
        ],
        [{"content": "ok"}],
    )
    assert _lines(result.stdout)[0]["tools"] == ["read_file", "grep", "glob"]

    result, _ = invoke(
        [
            "-p",
            "x",
            "--output-format",
            "stream-json",
            "--disallowed-tools",
            "execute_command,*_file",
        ],
        [{"content": "ok"}],
    )
    tools = _lines(result.stdout)[0]["tools"]
    assert "execute_command" not in tools and "read_file" not in tools
    assert "grep" in tools

    registry = ToolRegistry(
        [
            ToolSpec(name=n, description="", parameters={}, func=print)
            for n in ("a", "mcp__gh__issue", "mcp__gh__pr", "b")
        ]
    )
    removed = filter_tools(registry, parse_tool_list("a mcp__gh__*"), ["*pr"])
    assert registry.names() == ["a", "mcp__gh__issue"] and removed == [
        "mcp__gh__pr",
        "b",
    ]


def test_headless_denies_approval_tools_by_default(run):
    invoke, work = run
    script = [
        {"tool_calls": [_call("w1", "create_file", file_path="out.txt", content="x")]},
        {"content": "Could not write."},
    ]
    result, client = invoke(["-p", "write", "--output-format", "stream-json"], script)
    assert result.exit_code == 0
    end = next(e for e in _lines(result.stdout) if e["type"] == "tool_end")
    assert end["status"] == "denied" and "--approval yolo" in end["result"]
    assert not (work / "out.txt").exists()
    tool_message = next(m for m in client.requests[1] if m["role"] == "tool")
    assert "headless" in tool_message["content"]

    result, _ = invoke(["-p", "write", "--approval", "yolo"], script)
    assert result.exit_code == 0 and (work / "out.txt").read_text() == "x"


def test_headless_exit_codes(run):
    invoke, _ = run
    result, _ = invoke(["-p", "x", "--output-format", "json"], client_cls=FailingClient)
    assert result.exit_code == 1
    (payload,) = _lines(result.stdout)
    assert payload["is_error"] is True and "upstream 500" in payload["result"]

    result, _ = invoke(["-p", "x", "--output-format", "yaml"])
    assert result.exit_code == 2
    result, _ = invoke(["-p", "x", "also-an-argument"])
    assert result.exit_code == 2
    result, _ = invoke(["-p", "x", "--max-turns", "0"])
    assert result.exit_code == 2


def test_piped_stdin_never_hangs():
    read_fd, write_fd = os.pipe()  # a pipe nobody ever writes to
    with os.fdopen(read_fd) as stream:
        started = time.monotonic()
        assert cli.read_piped_stdin(stream, wait=0.2) == ""
        assert time.monotonic() - started < 2
    os.close(write_fd)

    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"log line\n")
    os.close(write_fd)
    with os.fdopen(read_fd) as stream:
        assert cli.read_piped_stdin(stream, wait=0.2) == "log line"
