"""Tool-call error tolerance (plan task 1.3)."""

import pytest

from neow.core.agent_loop import validate_history
from neow.core.approval import ApprovalMode, ApprovalPolicy
from neow.core.executor import (
    ToolDenied,
    ToolError,
    ToolExecutor,
    ToolInvalidArguments,
    ToolNotFound,
)
from tests.test_agent_loop import RecordingExecutor, _conversation


def _raw_call(call_id, name, arguments):
    return {"id": call_id, "function": {"name": name, "arguments": arguments}}


def _turn(arguments, executor=None):
    script = [
        {"content": "", "tool_calls": [_raw_call("c1", "read_file", arguments)]},
        {"content": "Recovered."},
    ]
    executor = executor or RecordingExecutor()
    conv, client = _conversation(script, executor)
    chunks = list(conv.get_response_stream("go"))
    result = next(m["content"] for m in conv.messages if m["role"] == "tool")
    return conv, client, executor, chunks, result


def test_bad_json_arguments_become_tool_error():
    conv, client, executor, _, result = _turn('{"file_path": "a.py"')

    assert result.startswith("Error: invalid JSON in tool arguments")
    assert "Re-issue the call" in result
    assert executor.calls == []
    assert len(client.requests) == 2  # the turn carried on
    assert conv.messages[-1]["content"] == "Recovered."
    assert validate_history(conv.messages) == []


def test_empty_arguments_mean_no_arguments():
    _, _, executor, _, result = _turn("")
    assert executor.calls == [("read_file", {})]
    assert result == "read_file ok"


def test_non_object_arguments_are_rejected():
    _, _, executor, _, result = _turn("[1, 2]")
    assert executor.calls == []
    assert "must be a JSON object" in result


def test_unknown_tool_lists_available():
    executor = ToolExecutor()
    with pytest.raises(ToolNotFound) as info:
        executor.execute("reed_file", {})
    message = str(info.value)
    assert "reed_file" in message
    assert "read_file" in message and "execute_command" in message
    assert isinstance(info.value, ToolError)


def _executor_with_spy():
    executor = ToolExecutor()
    calls = []
    executor.register_tool("read_file", lambda file_path: calls.append(file_path))
    asked = []
    executor.approval_policy = ApprovalPolicy(mode=ApprovalMode.ALWAYS_ASK)
    executor.approval_callback = lambda *args: asked.append(args) or True
    return executor, calls, asked


def test_missing_required_param_message():
    executor, calls, asked = _executor_with_spy()
    with pytest.raises(ToolInvalidArguments) as info:
        executor.execute("read_file", {})
    message = str(info.value)
    assert "missing required argument: file_path" in message
    assert "file_path (string, required)" in message
    assert calls == [] and asked == []  # never ran, never asked the user


def test_unexpected_param_message():
    executor, calls, asked = _executor_with_spy()
    with pytest.raises(ToolInvalidArguments) as info:
        executor.execute("read_file", {"path": "a.py"})
    message = str(info.value)
    assert "unexpected argument: path" in message
    assert "file_path (string, required)" in message
    assert calls == [] and asked == []


def test_valid_call_still_runs():
    executor, calls, _ = _executor_with_spy()
    executor.execute("read_file", {"file_path": "a.py"})
    assert calls == ["a.py"]


def test_denied_call_is_reported_as_denied():
    executor = ToolExecutor()
    executor.register_tool("read_file", lambda file_path: "ok")
    executor.approval_policy = ApprovalPolicy(mode=ApprovalMode.ALWAYS_ASK)
    executor.approval_callback = lambda *args: False

    with pytest.raises(ToolDenied, match="User denied"):
        executor.execute("read_file", {"file_path": "a.py"})

    _, _, _, chunks, result = _turn('{"file_path": "a.py"}', executor)
    ends = [
        c.progress for c in chunks if c.progress and c.progress["type"] == "tool_end"
    ]
    assert ends[0]["status"] == "denied"
    assert result.startswith("Error: User denied")


@pytest.mark.parametrize(
    "arguments, status",
    [('{"file_path": "a.py"}', "ok"), ("{", "error")],
)
def test_tool_end_reports_status(arguments, status):
    _, _, _, chunks, _ = _turn(arguments)
    ends = [
        c.progress for c in chunks if c.progress and c.progress["type"] == "tool_end"
    ]
    assert ends[0]["status"] == status
