"""First-run BYOK startup and safe model-dependent actions."""

import importlib
import json
import sys
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml
from click.testing import CliRunner


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    """Do not read real user settings or write startup artifacts to their home."""
    home = tmp_path / "home"
    work = tmp_path / "work"
    home.mkdir()
    work.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(work)
    for name in (
        "NEOW_DEEPSEEK_API_KEY",
        "NEOW_ANTHROPIC_API_KEY",
        "NEOW_OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    return SimpleNamespace(home=home, work=work)


@pytest.fixture
def startup(isolated_workspace, monkeypatch):
    cli = importlib.import_module("neow.cli.main")
    tui = importlib.import_module("neow.tui")
    run_tui = MagicMock(name="run_tui")
    repl = MagicMock(name="REPL")
    sessions = MagicMock(name="SessionManager")
    plugins = MagicMock(name="PluginManager")
    plugins.return_value.discover_and_load.return_value = []

    monkeypatch.setattr(cli, "setup_logger", MagicMock())
    monkeypatch.setattr(cli.logger, "error", MagicMock())
    monkeypatch.setattr(cli.console, "_file", None)
    monkeypatch.setattr(cli, "setup_tools", MagicMock())
    monkeypatch.setattr(cli, "setup_hooks", MagicMock(return_value=None))
    monkeypatch.setattr(cli, "setup_mcp", MagicMock(return_value=None))
    monkeypatch.setattr(cli, "PluginManager", plugins)
    monkeypatch.setattr(cli, "SessionManager", sessions)
    monkeypatch.setattr(cli, "REPL", repl)
    monkeypatch.setattr(cli, "tui_available", lambda: True)
    monkeypatch.setattr(tui, "run_tui", run_tui)
    monkeypatch.setattr("neow.tools.command.configure", MagicMock())
    monkeypatch.setattr("neow.tools.sandbox.configure", MagicMock())
    monkeypatch.setattr(
        "neow.core.memory.load_memory",
        lambda root: SimpleNamespace(warnings=[], text=""),
    )
    monkeypatch.setattr(
        "neow.core.checkpoints.ROOT", isolated_workspace.home / "checkpoints"
    )

    def invoke(args=(), *, stdin_tty=True, stdout_tty=True, input=None):
        # CliRunner normally replaces both streams with non-TTY wrappers.
        class TerminalRunner(CliRunner):
            @contextmanager
            def isolation(self, *args, **kwargs):
                with super().isolation(*args, **kwargs) as streams:
                    with monkeypatch.context() as terminal:
                        terminal.setattr(sys.stdin, "isatty", lambda: stdin_tty)
                        terminal.setattr(sys.stdout, "isatty", lambda: stdout_tty)
                        yield streams

        return TerminalRunner().invoke(
            cli.main, list(args), input=input, catch_exceptions=False
        )

    return SimpleNamespace(
        cli=cli,
        invoke=invoke,
        tui=run_tui,
        repl=repl,
        sessions=sessions,
        home=isolated_workspace.home,
        work=isolated_workspace.work,
    )


@pytest.mark.parametrize("args", [[], ["--tui"]])
def test_no_key_interactive_startup_enters_tui(startup, args):
    result = startup.invoke(args)

    assert result.exit_code == 0, result.output
    startup.tui.assert_called_once()
    startup.repl.assert_not_called()
    conversation = startup.tui.call_args.args[0]
    assert conversation.model_client is None
    assert "No API key" in conversation.model_setup_notice
    assert conversation.messages == []
    assert conversation.checkpoints.current is None
    assert not (startup.home / ".neow" / "config.json").exists()


def test_no_key_plain_startup_enters_repl(startup):
    result = startup.invoke(["--plain"])

    assert result.exit_code == 0, result.output
    startup.tui.assert_not_called()
    startup.repl.assert_called_once()
    startup.repl.return_value.start.assert_called_once()
    conversation = startup.repl.call_args.args[0]
    assert conversation.model_client is None
    assert "No API key" in conversation.model_setup_notice
    assert conversation.messages == []


def test_no_key_can_use_plain_fallback_when_tui_unavailable(startup, monkeypatch):
    monkeypatch.setattr(startup.cli, "tui_available", lambda: False)

    result = startup.invoke()

    assert result.exit_code == 0, result.output
    assert "falling back" in result.output
    startup.repl.return_value.start.assert_called_once()
    assert startup.repl.call_args.args[0].model_client is None


@pytest.mark.parametrize("args", [[], ["--plain"]])
def test_failed_connection_still_allows_interactive_setup(startup, monkeypatch, args):
    client = MagicMock()
    client.validate_connection.return_value = False
    monkeypatch.setattr(startup.cli, "create_model_client", lambda cfg, name: client)

    result = startup.invoke(args)

    assert result.exit_code == 0, result.output
    ui = startup.repl if args else startup.tui
    conversation = ui.call_args.args[0]
    assert conversation.model_client is None
    assert conversation.model_setup_notice == "Failed to connect to deepseek API"
    client.validate_connection.assert_called_once()
    client.chat.assert_not_called()
    client.chat_stream.assert_not_called()


@pytest.mark.parametrize("args", [[], ["--plain"]])
def test_configured_startup_keeps_validated_client(startup, monkeypatch, args):
    path = startup.home / ".neow" / "config.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "default_model": "router",
                "models": {
                    "router": {
                        "provider": "openai-compatible",
                        "model": "vendor/model",
                        "api_key": "stored-key",
                        "base_url": "https://example.com/v1",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    client = MagicMock(model="vendor/model", config_name="router")
    client.validate_connection.return_value = True
    create = MagicMock(return_value=client)
    monkeypatch.setattr(startup.cli, "create_model_client", create)

    result = startup.invoke(args)

    assert result.exit_code == 0, result.output
    assert create.call_args.args[1] == "router"
    ui = startup.repl if args else startup.tui
    conversation = ui.call_args.args[0]
    assert conversation.model_client is client
    assert conversation.model_setup_notice is None
    client.validate_connection.assert_called_once()
    client.chat.assert_not_called()
    client.chat_stream.assert_not_called()


@pytest.mark.parametrize(
    "args, stdin_tty, stdout_tty, input",
    [
        (["hello"], True, True, None),
        (["--plain", "hello"], True, True, None),
        (["-p", "hello"], True, True, None),
        ([], False, True, "hello\n"),
        ([], False, True, ""),
        ([], True, False, None),
        (["--plain"], False, False, ""),
        (["--tui"], False, True, ""),
    ],
)
def test_no_key_noninteractive_startup_fails(
    startup, args, stdin_tty, stdout_tty, input
):
    result = startup.invoke(
        args, stdin_tty=stdin_tty, stdout_tty=stdout_tty, input=input
    )

    assert result.exit_code == 1
    assert "No API key" in result.output
    startup.tui.assert_not_called()
    startup.repl.assert_not_called()
    startup.sessions.assert_not_called()


@pytest.mark.parametrize("output_format", ["json", "stream-json"])
def test_no_key_headless_keeps_machine_readable_failure(startup, output_format):
    result = startup.invoke(["-p", "hello", "--output-format", output_format])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["type"] == "result"
    assert payload["is_error"] is True
    assert "No API key" in payload["result"]
    startup.tui.assert_not_called()
    startup.repl.assert_not_called()


def test_no_key_message_file_is_not_interactive_setup(startup):
    message = startup.work / "prompt.txt"
    message.write_text("hello", encoding="utf-8")

    result = startup.invoke(["--message-file", str(message)])

    assert result.exit_code == 1
    assert "No API key" in result.output
    startup.tui.assert_not_called()
    startup.repl.assert_not_called()


def test_invalid_config_file_is_not_hidden_by_onboarding(startup):
    path = startup.work / "broken.json"
    path.write_text("{", encoding="utf-8")

    result = startup.invoke(["--config", str(path)])

    assert result.exit_code == 1
    assert "Invalid config file" in result.output
    startup.tui.assert_not_called()
    startup.repl.assert_not_called()


@pytest.mark.parametrize("args", [["hello"], ["-p", "hello"]])
def test_failed_connection_is_still_fatal_for_one_shot(startup, monkeypatch, args):
    client = MagicMock()
    client.validate_connection.return_value = False
    monkeypatch.setattr(startup.cli, "create_model_client", lambda cfg, name: client)

    result = startup.invoke(args)

    assert result.exit_code == 1
    assert "Failed to connect to deepseek API" in result.output
    startup.tui.assert_not_called()
    startup.repl.assert_not_called()
    client.chat.assert_not_called()
    client.chat_stream.assert_not_called()


def _unconfigured_conversation():
    from neow.core.conversation import ConversationManager

    conversation = ConversationManager(None, tool_executor=MagicMock())
    conversation.add_message("user", "previous question")
    conversation.messages.append(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "unfinished",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        }
    )
    conversation.hooks = MagicMock()
    conversation.checkpoints = MagicMock()
    conversation.context_manager = MagicMock()
    conversation.token_tracker = MagicMock()
    conversation.build_context_message = MagicMock()
    conversation._pending_images = [{"type": "image", "source": {"data": "image"}}]
    conversation.context_files = {"notes.txt": "context"}
    conversation.pending_lint_feedback = "keep this feedback"
    return conversation


@pytest.mark.parametrize("stream", [False, True])
def test_unconfigured_chat_fails_before_any_turn_side_effects(stream):
    from neow.models.base import ModelNotConfiguredError

    conversation = _unconfigured_conversation()
    messages = deepcopy(conversation.messages)
    pending_images = deepcopy(conversation._pending_images)

    with pytest.raises(ModelNotConfiguredError, match="Use /model add"):
        if stream:
            list(conversation.get_response_stream("new message"))
        else:
            conversation.get_response("new message")

    assert conversation.messages == messages
    assert conversation._pending_images == pending_images
    assert conversation.context_files == {"notes.txt": "context"}
    assert conversation.pending_lint_feedback == "keep this feedback"
    assert conversation._structure_injected is False
    conversation.hooks.run.assert_not_called()
    conversation.checkpoints.begin_turn.assert_not_called()
    conversation.build_context_message.assert_not_called()
    conversation.context_manager.get_relevant_files.assert_not_called()
    conversation.context_manager.get_project_structure.assert_not_called()
    conversation.token_tracker.record.assert_not_called()
    conversation.tool_executor.execute.assert_not_called()


@pytest.mark.parametrize(
    "method", ["compact", "compact_incremental", "compact_with_handoff"]
)
def test_unconfigured_compaction_keeps_existing_state(method):
    from neow.core.conversation import ConversationManager
    from neow.models.base import ModelNotConfiguredError

    conversation = ConversationManager(None, token_tracker=MagicMock())
    for index in range(8):
        conversation.add_message("user" if index % 2 == 0 else "assistant", "x" * 100)
    conversation.context_files = {"notes.txt": "important"}
    conversation.web_cache = {"https://example.com": "cached"}
    conversation._structure_injected = True
    original = deepcopy(conversation.messages)
    args = {"keep_recent_tokens": 1} if method == "compact_incremental" else {}

    with pytest.raises(ModelNotConfiguredError, match="No model configured"):
        getattr(conversation, method)(**args)

    assert conversation.messages == original
    assert conversation.context_files == {"notes.txt": "important"}
    assert conversation.web_cache == {"https://example.com": "cached"}
    assert conversation._structure_injected is True
    conversation.token_tracker.record.assert_not_called()


def test_unconfigured_empty_compaction_remains_noop():
    from neow.core.conversation import ConversationManager

    conversation = ConversationManager(None)

    assert conversation.compact() == "Nothing to compact."
    assert conversation.compact_incremental() == "Too few messages to compact."
    assert conversation.compact_with_handoff() == ""
    assert conversation.messages == []


@pytest.mark.parametrize("suffix", [".json", ".yaml"])
def test_default_model_survives_reload_without_copying_env_key(
    isolated_workspace, monkeypatch, suffix
):
    from neow.core.config import Config

    path = isolated_workspace.work / ("settings" + suffix)
    data = {
        "models": {"router": {"provider": "openai-compatible", "model": "vendor/m"}},
        "tools": {"enabled": ["read_file"]},
    }
    path.write_text(
        yaml.safe_dump(data) if suffix == ".yaml" else json.dumps(data),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEOW_DEEPSEEK_API_KEY", "environment-only-secret")
    config = Config(path)
    assert config.models["deepseek"]["api_key"] == "environment-only-secret"

    assert config.set_default_model("router") == path

    saved = path.read_text(encoding="utf-8")
    assert "environment-only-secret" not in saved
    reloaded = Config(path)
    assert reloaded.default_model == "router"
    assert reloaded.models["router"]["model"] == "vendor/m"
    assert reloaded.tools["enabled"] == ["read_file"]
    assert config.default_model == "router"


def test_default_model_persists_to_first_run_user_config(
    isolated_workspace, monkeypatch
):
    from neow.core.config import Config

    monkeypatch.setenv("NEOW_OPENAI_API_KEY", "environment-only-secret")
    config = Config()

    path = config.set_default_model("openai")

    assert path == isolated_workspace.home / ".neow" / "config.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"default_model": "openai"}
    assert Config().default_model == "openai"


def test_default_model_save_failure_does_not_change_state(
    isolated_workspace, monkeypatch
):
    from neow.core.config import Config, ConfigError

    path = isolated_workspace.work / "settings.json"
    path.write_text('{"default_model": "deepseek"}', encoding="utf-8")
    original = path.read_text(encoding="utf-8")
    config = Config(path)
    monkeypatch.setattr("neow.core.config.os.replace", MagicMock(side_effect=OSError))

    with pytest.raises(ConfigError, match="Could not save model configuration"):
        config.set_default_model("openai")

    assert config.default_model == "deepseek"
    assert path.read_text(encoding="utf-8") == original
    assert sorted(isolated_workspace.work.iterdir()) == [path]


def test_default_model_rejects_unknown_entry_without_writing(isolated_workspace):
    from neow.core.config import Config, ConfigError

    path = isolated_workspace.work / "new.json"
    config = Config(path)

    with pytest.raises(ConfigError, match="not found"):
        config.set_default_model("nonexistent")

    with pytest.raises(ConfigError, match="not found"):
        config.resolve_model_name("nonexistent")

    with pytest.raises(ConfigError, match="not found"):
        config.get_model_config("nonexistent")

    assert config.default_model == "deepseek"
    assert not path.exists()


@pytest.mark.parametrize(
    "selector, canonical",
    [
        ("DeepSeek", "deepseek"),
        ("deepseek-v4-flash", "deepseek"),
        ("gpt", "openai"),
    ],
)
def test_default_model_normalizes_legacy_selectors(
    isolated_workspace, selector, canonical
):
    from neow.core.config import Config

    path = isolated_workspace.work / "settings.json"
    path.write_text("{}", encoding="utf-8")
    config = Config(path)

    assert config.resolve_model_name(selector) == canonical
    assert config.get_model_config(selector) is config.models[canonical]
    config.set_default_model(selector)

    assert config.default_model == canonical
    assert Config(path).default_model == canonical
    assert json.loads(path.read_text(encoding="utf-8"))["default_model"] == canonical


def test_default_model_keeps_exact_custom_name_over_builtin_alias(isolated_workspace):
    from neow.core.config import Config

    path = isolated_workspace.work / "settings.json"
    path.write_text(
        json.dumps(
            {"models": {"gpt": {"provider": "openai-compatible", "model": "my-model"}}}
        ),
        encoding="utf-8",
    )
    config = Config(path)

    assert config.resolve_model_name("gpt") == "gpt"
    assert config.get_model_config("gpt")["model"] == "my-model"
    config.set_default_model("gpt")

    assert config.default_model == "gpt"
    assert Config(path).default_model == "gpt"
    assert json.loads(path.read_text(encoding="utf-8"))["default_model"] == "gpt"
