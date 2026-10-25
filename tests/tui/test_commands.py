"""Command dispatcher tests (plan task 13)."""

from pathlib import Path

import pytest

from neow.cli.commands import Command, ParsedCommand
from neow.core.approval import ApprovalMode, ApprovalPolicy
from neow.tui.commands import CommandDispatcher


class ConfigStub:
    def __init__(self):
        self._config = {
            "approval": {"mode": "write"},
            "lint_test": {"auto_lint": False, "auto_test": False},
        }

    def save_model(self, name, entry):
        pass


class FakeConv:
    def __init__(self, **attrs):
        self.messages = []
        self.pending_lint_feedback = None
        self.context_files = attrs.pop("context_files", [])
        self._attrs = attrs

    def list_context_files(self):
        return list(self.context_files)

    def add_context_file(self, path):
        exc = self._attrs.get("add_context_file")
        if exc:
            raise exc
        return f"Added {path}"

    def drop_context_file(self, path):
        exc = self._attrs.get("drop_context_file")
        if exc:
            raise exc
        return f"Dropped {path}"

    def clear_history(self):
        self.messages.clear()

    def queue_image(self, path):
        return f"Queued image: {path}"

    def compact(self):
        return "compacted"

    def compact_incremental(self, keep_recent_tokens=4000):
        return "incremental"

    def compact_with_handoff(self):
        return "handoff"


def FakeConvWithContext(files):
    return FakeConv(context_files=files)


def make_dispatcher(**kwargs):
    defaults = dict(conversation=FakeConv(), config=ConfigStub())
    defaults.update(kwargs)
    return CommandDispatcher(**defaults)


def test_ls_lists_context_files():
    dispatcher = make_dispatcher(conversation=FakeConvWithContext(["a.py"]))
    assert "a.py" in dispatcher.dispatch(ParsedCommand(Command.LS)).text


def test_add_reports_file_not_found():
    dispatcher = make_dispatcher(
        conversation=FakeConv(add_context_file=FileNotFoundError("nope"))
    )
    result = dispatcher.dispatch(ParsedCommand(Command.ADD, "x.py"))
    assert "nope" in result.text and result.kind == "error"


def test_approval_mode_switch_updates_policy_and_config():
    policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
    config = ConfigStub()
    dispatcher = make_dispatcher(approval_policy=policy, config=config)
    dispatcher.dispatch(ParsedCommand(Command.APPROVAL, "yolo"))
    assert policy.mode == ApprovalMode.YOLO
    assert config._config["approval"]["mode"] == "yolo"


def test_verbose_toggles():
    dispatcher = make_dispatcher()
    assert dispatcher.dispatch(ParsedCommand(Command.VERBOSE)).text
    assert dispatcher.verbose is True


def test_exit_returns_exit_signal():
    assert make_dispatcher().dispatch(ParsedCommand(Command.EXIT)).should_exit


def test_compact_returns_compaction_kind():
    result = make_dispatcher().dispatch(ParsedCommand(Command.COMPACT))
    assert result.kind == "compaction" and result.text


def test_image_requires_arg():
    result = make_dispatcher().dispatch(ParsedCommand(Command.IMAGE, ""))
    assert result.kind == "error" and "Usage" in result.text


def test_image_queues_file():
    result = make_dispatcher().dispatch(ParsedCommand(Command.IMAGE, "shot.png"))
    assert result.kind != "error"
    assert "Queued image: shot.png" in result.text


def test_imgdiff_requires_two_args():
    result = make_dispatcher().dispatch(ParsedCommand(Command.IMGDIFF, "only_one.png"))
    assert result.kind == "error" and "Usage" in result.text


def test_imgdiff_computes_diff_and_queues_result(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (5, 5), (255, 255, 255)).save(before)
    Image.new("RGB", (5, 5), (0, 0, 0)).save(after)

    result = make_dispatcher().dispatch(
        ParsedCommand(Command.IMGDIFF, f"{before} {after}")
    )

    assert result.kind != "error"
    assert "differs" in result.text and "no inline preview" in result.text


def test_imgdiff_reports_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = make_dispatcher().dispatch(
        ParsedCommand(
            Command.IMGDIFF, f"{tmp_path / 'nope.png'} {tmp_path / 'nope2.png'}"
        )
    )
    assert result.kind == "error"


def test_unknown_falls_back_to_plugin_then_error():
    dispatcher = make_dispatcher(plugin_api=None)
    result = dispatcher.dispatch(ParsedCommand(None, None, raw_command="nope"))
    assert "Unknown command" in result.text


def test_ui_commands_delegate_to_hooks():
    calls = []
    dispatcher = make_dispatcher(hooks={"help": lambda: calls.append("help")})
    dispatcher.dispatch(ParsedCommand(Command.HELP))
    assert calls == ["help"]


def test_model_name_switches_instead_of_opening_picker(monkeypatch):
    from types import SimpleNamespace

    client = SimpleNamespace(validate_connection=lambda: True)
    monkeypatch.setattr(
        "neow.cli.main.create_model_client", lambda config, name: client
    )
    persisted = []
    config = SimpleNamespace(
        resolve_model_alias=lambda name: name, set_default_model=persisted.append
    )
    calls = []
    dispatcher = make_dispatcher(
        config=config, hooks={"model": lambda: calls.append("picker")}
    )
    result = dispatcher.dispatch(ParsedCommand(Command.MODEL, "router"))
    assert result.kind == "info"
    assert dispatcher.conversation.model_client is client
    assert persisted == ["router"]
    assert calls == []


def test_model_add_and_magpie_use_hooks():
    calls = []
    dispatcher = make_dispatcher(
        hooks={
            "model_add": lambda: calls.append("add"),
            "model_sync": lambda: calls.append("sync"),
        }
    )
    dispatcher.dispatch(ParsedCommand(Command.MODEL, "add"))
    dispatcher.dispatch(ParsedCommand(Command.MODEL, "magpie"))
    assert calls == ["add", "sync"]


def test_effort_uses_hook_when_no_args():
    calls = []
    client = type("FakeClient", (), {"effort": "low", "config_name": "m"})()
    conv = FakeConv()
    conv.model_client = client
    dispatcher = make_dispatcher(
        conversation=conv,
        hooks={"effort": lambda: calls.append("picker")},
    )
    dispatcher.dispatch(ParsedCommand(Command.EFFORT))
    assert calls == ["picker"]


def test_effort_sets_directly_with_args():
    calls = []
    client = type("FakeClient", (), {"effort": "off", "config_name": "m"})()
    conv = FakeConv()
    conv.model_client = client
    dispatcher = make_dispatcher(
        conversation=conv,
        hooks={"effort": lambda: calls.append("picker")},
    )
    res = dispatcher.dispatch(ParsedCommand(Command.EFFORT, "high"))
    assert res.kind == "info"
    assert client.effort == "high"
    assert calls == []


@pytest.mark.parametrize(
    "cmd,hook_name",
    [
        (Command.APPROVAL, "approval"),
        (Command.ARCHITECT, "architect"),
        (Command.CODE, "code"),
        (Command.MODE, "mode"),
        (Command.VERBOSE, "verbose"),
        (Command.DROP, "drop"),
        (Command.ADD, "add"),
        (Command.LS, "ls"),
        (Command.IMAGE, "image"),
        (Command.IMGDIFF, "imgdiff"),
        (Command.MEMORY, "memory"),
        (Command.MCP, "mcp"),
        (Command.WEB, "web"),
        (Command.SAVE, "save"),
        (Command.COMPACT, "compact"),
        (Command.EXPORT, "export"),
        (Command.REWIND, "rewind"),
        (Command.THINK, "think"),
        (Command.THINKING, "thinking"),
        (Command.CLEAR, "clear"),
        (Command.COMMIT, "commit"),
        (Command.UNDO, "undo"),
        (Command.LINT, "lint"),
        (Command.TEST, "test"),
        (Command.EFFORT, "effort"),
        (Command.GOAL, "goal"),
    ],
)
def test_all_interactive_commands_without_args_invoke_hook(cmd, hook_name):
    called = []
    client = type("FakeClient", (), {"effort": "low", "config_name": "m"})()
    conv = FakeConv()
    conv.model_client = client
    dispatcher = make_dispatcher(
        conversation=conv,
        hooks={hook_name: lambda: called.append(True)},
    )
    dispatcher.dispatch(ParsedCommand(cmd, ""))
    assert called == [True]


def test_command_with_args_bypasses_hook():
    called = []
    policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
    config = ConfigStub()
    conv = FakeConv(context_files=["a.py"])
    dispatcher = make_dispatcher(
        conversation=conv,
        config=config,
        approval_policy=policy,
        hooks={
            "approval": lambda: called.append("approval"),
            "drop": lambda: called.append("drop"),
        },
    )
    # With args, approval updates directly without hook
    res = dispatcher.dispatch(ParsedCommand(Command.APPROVAL, "yolo"))
    assert res.kind == "info"
    assert policy.mode == ApprovalMode.YOLO
    assert called == []

    # With args, drop executes directly without hook
    res = dispatcher.dispatch(ParsedCommand(Command.DROP, "a.py"))
    assert res.kind == "info"
    assert called == []

    # Thinking commands directly toggle or set show_thinking
    res = dispatcher.dispatch(ParsedCommand(Command.THINKING, "off"))
    assert res.kind == "info"
    assert conv.show_thinking is False
    assert config._config.get("tui", {}).get("show_thinking") is False

    res = dispatcher.dispatch(ParsedCommand(Command.THINK, "on"))
    assert res.kind == "info"
    assert conv.show_thinking is True
    assert config._config.get("tui", {}).get("show_thinking") is True


def test_init_command_submits_prompt_directly():
    submitted = []
    dispatcher = make_dispatcher(
        hooks={"submit": submitted.append},
    )
    res = dispatcher.dispatch(ParsedCommand(Command.INIT, ""))
    assert res.kind == "info"
    assert len(submitted) == 1
    assert "AGENTS.md" in submitted[0]


def test_goal_command_lifecycle_and_helpers():
    from neow.core.goal import (
        GOAL_COMPLETION_MARKER,
        GoalState,
        build_goal_continuation_prompt,
        build_goal_initial_prompt,
        is_goal_achieved,
    )

    conv = FakeConv()
    submitted = []
    dispatcher = make_dispatcher(
        conversation=conv,
        hooks={"submit": submitted.append},
    )

    # Start goal with args directly
    res = dispatcher.dispatch(ParsedCommand(Command.GOAL, "fix all tests"))
    assert "fix all tests" in res.text
    assert conv.goal_state is not None
    assert conv.goal_state.active is True
    assert conv.goal_state.goal == "fix all tests"
    assert len(submitted) == 1
    assert "fix all tests" in submitted[0]

    # Status check
    status_res = dispatcher.dispatch(ParsedCommand(Command.GOAL, "status"))
    assert "fix all tests" in status_res.text

    # Stop goal
    stop_res = dispatcher.dispatch(ParsedCommand(Command.GOAL, "stop"))
    assert "已停止" in stop_res.text
    assert conv.goal_state.active is False

    # Check goal completion logic
    assert (
        is_goal_achieved(
            "still working", [{"id": "1", "content": "a", "status": "in_progress"}]
        )
        is False
    )
    assert (
        is_goal_achieved(
            f"done {GOAL_COMPLETION_MARKER}",
            [{"id": "1", "content": "a", "status": "pending"}],
        )
        is False
    )
    assert (
        is_goal_achieved(
            f"all done {GOAL_COMPLETION_MARKER}",
            [{"id": "1", "content": "a", "status": "completed"}],
        )
        is True
    )
    assert (
        is_goal_achieved(
            "finished steps", [{"id": "1", "content": "a", "status": "completed"}]
        )
        is True
    )

    cont = build_goal_continuation_prompt(
        GoalState(goal="ship feature", current_round=2, max_rounds=5),
        [{"id": "1", "content": "write unit tests", "status": "pending"}],
    )
    assert "2/5" in cont
    assert "write unit tests" in cont
    assert GOAL_COMPLETION_MARKER in build_goal_initial_prompt("ship feature")
