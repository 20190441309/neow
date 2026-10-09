"""Cancellable command execution (plan task 1.5)."""

import inspect
import os
import sys
import threading
import time

import pytest

from neow.core.agent_loop import validate_history
from neow.core.cancellation import CancelToken, cancellation_scope
from neow.tools import command
from neow.tools.command import execute_command
from tests.test_agent_loop import _call, _conversation

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell syntax")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers kill(0); check its state where we can.
    try:
        with open(f"/proc/{pid}/stat") as handle:
            return handle.read().split()[2] != "Z"
    except OSError:
        return True


def _cancel_after(token: CancelToken, seconds: float) -> None:
    timer = threading.Timer(seconds, token.cancel)
    timer.daemon = True
    timer.start()


@posix_only
def test_cancel_kills_running_command(tmp_path):
    pid_file = tmp_path / "child.pid"
    token = CancelToken()
    _cancel_after(token, 0.3)
    started = time.monotonic()
    with cancellation_scope(token):
        # The grandchild must die too, not just the shell.
        result = execute_command(f"sleep 30 & echo $! > {pid_file}; wait")
    elapsed = time.monotonic() - started

    assert elapsed < 3
    assert result.startswith("Error: cancelled")
    child = int(pid_file.read_text())
    deadline = time.monotonic() + 2
    while _alive(child) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(child)


@posix_only
def test_timeout_kills_command_and_reports_partial_output():
    started = time.monotonic()
    result = execute_command("echo started; sleep 30", timeout=1)
    assert time.monotonic() - started < 4
    assert result.startswith("Error: Command timed out after 1 seconds")
    assert "started" in result


def test_default_timeout_is_120():
    default = inspect.signature(execute_command).parameters["timeout"].default
    assert default == 120


def test_timeout_is_clamped_to_maximum(monkeypatch):
    monkeypatch.setattr(command, "_max_timeout", 600)
    assert command.effective_timeout(10_000) == 600
    assert command.effective_timeout(0) == 120
    assert command.effective_timeout(5) == 5
    command.configure(max_timeout=900)
    assert command.effective_timeout(10_000) == 900


@posix_only
def test_failure_reports_exit_code_stdout_and_stderr():
    result = execute_command("echo 2 failed in stdout; echo boom >&2; exit 3")
    assert result.startswith("Error: exit code 3")
    assert "2 failed in stdout" in result
    assert "boom" in result


@posix_only
def test_cancel_then_new_turn_history_valid():
    class ShellExecutor:
        def execute(self, name, args):
            return execute_command(args["command"])

    script = [
        {
            "content": "",
            "tool_calls": [_call("c1", "execute_command", command="sleep 30")],
        },
        {"content": "never reached"},
    ]
    conv, client = _conversation(script, ShellExecutor())
    token = CancelToken()
    _cancel_after(token, 0.3)
    started = time.monotonic()
    list(conv.get_response_stream("run it", cancel=token))

    assert time.monotonic() - started < 3
    assert len(client.requests) == 1
    assert validate_history(conv.messages) == []
    result = next(m["content"] for m in conv.messages if m["role"] == "tool")
    assert result.startswith("Error: cancelled")

    client.replies = [{"content": "Fresh answer."}]
    list(conv.get_response_stream("next"))
    assert conv.messages[-1]["content"] == "Fresh answer."
    assert validate_history(conv.messages) == []
