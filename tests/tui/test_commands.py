"""Command dispatcher tests (plan task 13)."""

from neow.cli.commands import Command, ParsedCommand
from neow.core.approval import ApprovalMode, ApprovalPolicy
from neow.tui.commands import CommandDispatcher


class ConfigStub:
    def __init__(self):
        self._config = {
            "approval": {"mode": "write"},
            "lint_test": {"auto_lint": False, "auto_test": False},
        }


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


def test_unknown_falls_back_to_plugin_then_error():
    dispatcher = make_dispatcher(plugin_api=None)
    result = dispatcher.dispatch(ParsedCommand(None, None, raw_command="nope"))
    assert "Unknown command" in result.text


def test_ui_commands_delegate_to_hooks():
    calls = []
    dispatcher = make_dispatcher(hooks={"help": lambda: calls.append("help")})
    dispatcher.dispatch(ParsedCommand(Command.HELP))
    assert calls == ["help"]
