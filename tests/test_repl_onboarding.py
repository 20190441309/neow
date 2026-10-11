"""The plain REPL can configure a first BYOK model without a startup key."""

import json
from unittest.mock import MagicMock, patch

import click
import pytest

from neow.cli.commands import parse_command
from neow.cli.repl import REPL
from neow.core.config import Config, ConfigError
from neow.core.conversation import ConversationManager


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    return Config(path)


@pytest.fixture
def repl(config, monkeypatch):
    monkeypatch.setattr(REPL, "_setup_session", lambda self: None)
    return REPL(ConversationManager(None), config=config, streaming=False)


def byok_prompts():
    return [
        "my-router",
        "openai-compatible",
        "https://example.com/v1",
        "vendor/my-model",
        "",
        "private-key",
    ]


def new_client(connected=True):
    client = MagicMock()
    client.model = "vendor/my-model"
    client.validate_connection.return_value = connected
    return client


def test_start_without_model_keeps_repl_available(repl):
    with (
        patch.object(repl, "_get_input", side_effect=["hello", "/model", "/exit"]),
        patch("neow.cli.repl.print_welcome") as welcome,
        patch("neow.cli.repl.print_user_message") as user_message,
        patch("neow.cli.repl.print_info") as info,
        patch("neow.cli.repl.print_error") as error,
    ):
        repl.start()

    welcome.assert_called_once()
    assert welcome.call_args.kwargs["model"] == "not configured"
    assert "/model add" in " ".join(str(call) for call in info.call_args_list)
    error.assert_called_once()
    assert user_message.call_count == 3
    assert user_message.call_args_list[0].kwargs["msg_num"] is None
    assert repl._turns_started == 0
    assert repl._msg_counter == 0
    assert repl.conversation.messages == []


def test_start_displays_unavailable_model_notice(repl):
    repl.conversation.model_setup_notice = "Failed to connect to the saved model"
    with (
        patch.object(repl, "_get_input", return_value="/exit"),
        patch("neow.cli.repl.print_welcome"),
        patch("neow.cli.repl.print_user_message"),
        patch("neow.cli.repl.print_warning") as warning,
    ):
        repl.start()

    assert "Failed to connect" in warning.call_args.args[0]


def test_normal_start_configures_first_model_and_accepts_prompt(repl, config):
    client = new_client()
    repl.conversation.model_setup_notice = "No startup key"
    with (
        patch.object(repl, "_get_input", side_effect=["/model add", "hello", "/exit"]),
        patch("click.prompt", side_effect=byok_prompts()),
        patch("neow.cli.main.create_model_client", return_value=client),
        patch.object(repl.conversation, "get_response") as response,
        patch("neow.cli.repl.print_welcome"),
        patch("neow.cli.repl.print_user_message") as user_message,
        patch("neow.cli.repl.print_assistant_message"),
    ):
        repl.start()

    response.assert_called_once_with("hello")
    assert repl.conversation.model_client is client
    assert repl.conversation.model_setup_notice is None
    assert Config(config.source_path).default_model == "my-router"
    assert user_message.call_args_list[0].kwargs["msg_num"] is None
    assert user_message.call_args_list[1].kwargs["msg_num"] == 1
    assert repl._turns_started == 1


@pytest.mark.parametrize(
    "streaming, architect", [(False, False), (True, False), (True, True)]
)
def test_prompt_without_model_has_no_side_effects(repl, streaming, architect):
    repl.streaming = streaming
    repl.architect_mode = architect
    repl.web_fetcher = MagicMock()
    repl.event_bus = MagicMock()
    repl.token_tracker = MagicMock()
    repl.conversation.pending_lint_feedback = "lint feedback"

    with (
        patch.object(repl.conversation, "get_response") as response,
        patch.object(repl, "_process_input_stream") as stream,
        patch.object(repl, "_process_architect") as planner,
        patch.object(repl, "_maybe_auto_compact") as compact,
        patch("neow.cli.repl.print_error") as error,
    ):
        repl._process_input("Please check https://example.com")

    assert "/model add" in error.call_args.args[0]
    repl.web_fetcher.fetch.assert_not_called()
    repl.event_bus.emit.assert_not_called()
    repl.token_tracker.check_max_tokens.assert_not_called()
    response.assert_not_called()
    stream.assert_not_called()
    planner.assert_not_called()
    compact.assert_not_called()
    assert repl.conversation.messages == []
    assert repl.conversation.web_cache == {}
    assert repl.conversation.pending_lint_feedback == "lint feedback"
    assert repl._last_activity_time == 0.0
    assert repl._msg_counter == 0


def test_model_command_without_client_lists_models(repl):
    with patch("neow.cli.repl.print_info") as info:
        assert repl._handle_command(parse_command("/model")) is False

    output = " ".join(str(call) for call in info.call_args_list)
    assert "Current model: not configured" in output
    assert "Available models" in output
    assert "/model add" in output


def test_first_byok_save_activates_and_persists_default(repl, config):
    client = new_client()

    with (
        patch("click.prompt", side_effect=byok_prompts()) as prompt,
        patch("neow.cli.main.create_model_client", return_value=client) as factory,
        patch.object(
            config, "set_default_model", wraps=config.set_default_model
        ) as default,
    ):
        repl._handle_command(parse_command("/model add"))

    factory.assert_called_once_with(config, "my-router")
    client.validate_connection.assert_called_once_with()
    default.assert_called_once_with("my-router")
    assert repl.conversation.model_client is client
    assert config.default_model == "my-router"
    assert Config(config.source_path).default_model == "my-router"
    assert config.models["my-router"]["model"] == "vendor/my-model"
    assert prompt.call_args_list[-1].kwargs["hide_input"] is True


def test_first_byok_bad_connection_keeps_saved_entry(repl, config):
    client = new_client(connected=False)

    with (
        patch("click.prompt", side_effect=byok_prompts()),
        patch("neow.cli.main.create_model_client", return_value=client),
        patch.object(config, "set_default_model") as default,
        patch("neow.cli.repl.print_error") as error,
    ):
        assert repl._handle_command(parse_command("/model add")) is False

    default.assert_not_called()
    assert repl.conversation.model_client is None
    assert Config(config.source_path).models["my-router"]["model"] == "vendor/my-model"
    assert "/model my-router" in error.call_args.args[0]


def test_saved_first_model_can_be_retried_after_connection_failure(repl, config):
    client = new_client(connected=False)
    with (
        patch("click.prompt", side_effect=byok_prompts()),
        patch("neow.cli.main.create_model_client", return_value=client),
    ):
        repl._handle_command(parse_command("/model add"))
        client.validate_connection.return_value = True
        repl._handle_command(parse_command("/model my-router"))

    assert repl.conversation.model_client is client
    assert Config(config.source_path).default_model == "my-router"


def test_first_byok_factory_failure_keeps_saved_entry(repl, config):
    with (
        patch("click.prompt", side_effect=byok_prompts()),
        patch(
            "neow.cli.main.create_model_client", side_effect=ConfigError("Unavailable")
        ),
        patch.object(config, "set_default_model") as default,
    ):
        assert repl._handle_command(parse_command("/model add")) is False

    default.assert_not_called()
    assert repl.conversation.model_client is None
    assert "my-router" in Config(config.source_path).models


def test_byok_save_does_not_switch_existing_client(repl, config):
    original = new_client()
    repl.conversation.model_client = original
    default_before = config.default_model

    with (
        patch("click.prompt", side_effect=byok_prompts()),
        patch("neow.cli.main.create_model_client") as factory,
        patch.object(config, "set_default_model") as default,
        patch("neow.cli.repl.print_info") as info,
    ):
        repl._handle_command(parse_command("/model add"))

    factory.assert_not_called()
    default.assert_not_called()
    assert repl.conversation.model_client is original
    assert config.default_model == default_before
    assert "my-router" in Config(config.source_path).models
    assert "/model my-router" in info.call_args.args[0]


def test_byok_environment_reference_does_not_prompt_for_key(repl, config, monkeypatch):
    monkeypatch.setenv("BYOK_KEY", "environment-secret")
    prompts = byok_prompts()[:-1]
    prompts[-1] = " BYOK_KEY "

    with (
        patch("click.prompt", side_effect=prompts) as prompt,
        patch("neow.cli.main.create_model_client", return_value=new_client()),
    ):
        repl._handle_command(parse_command("/model add"))

    assert prompt.call_count == 5
    entry = Config(config.source_path).models["my-router"]
    assert entry["api_key_env"] == "BYOK_KEY"
    assert entry["api_key"] == ""
    assert "environment-secret" not in config.source_path.read_text()


def test_cancelled_byok_does_not_save_or_activate(repl, config):
    before = config.source_path.read_text()
    with (
        patch("click.prompt", side_effect=click.Abort),
        patch("neow.cli.main.create_model_client") as factory,
    ):
        repl._handle_command(parse_command("/model add"))

    factory.assert_not_called()
    assert config.source_path.read_text() == before
    assert repl.conversation.model_client is None


def test_byok_save_failure_does_not_attempt_activation(repl, config):
    with (
        patch("click.prompt", side_effect=byok_prompts()),
        patch.object(config, "save_model", side_effect=ConfigError("Cannot write")),
        patch("neow.cli.main.create_model_client") as factory,
    ):
        repl._handle_command(parse_command("/model add"))

    factory.assert_not_called()
    assert repl.conversation.model_client is None
    assert "my-router" not in config.models


def test_model_switch_persists_selection_before_replacing_client(repl, config):
    original = new_client()
    selected = new_client()
    repl.conversation.model_client = original
    repl.conversation.messages = [{"role": "user", "content": "Earlier turn"}]
    saved_default = config.set_default_model

    def persist(name):
        assert repl.conversation.model_client is original
        return saved_default(name)

    with (
        patch("neow.cli.main.create_model_client", return_value=selected),
        patch.object(config, "set_default_model", side_effect=persist) as default,
    ):
        repl._handle_command(parse_command("/model gpt"))

    default.assert_called_once_with("openai")
    assert repl.conversation.model_client is selected
    assert Config(config.source_path).default_model == "openai"
    assert repl.conversation.messages == [{"role": "user", "content": "Earlier turn"}]


@pytest.mark.parametrize("has_active_client", [False, True])
def test_model_default_save_failure_keeps_previous_client(
    repl, config, has_active_client
):
    original = new_client() if has_active_client else None
    repl.conversation.model_client = original
    before = config.source_path.read_text()
    selected = new_client()

    with (
        patch("neow.cli.main.create_model_client", return_value=selected),
        patch.object(
            config, "set_default_model", side_effect=ConfigError("Cannot write")
        ),
        patch("neow.cli.repl.print_error") as error,
    ):
        repl._handle_command(parse_command("/model openai"))

    selected.validate_connection.assert_called_once_with()
    error.assert_called_once()
    assert repl.conversation.model_client is original
    assert config.source_path.read_text() == before
    assert config.default_model == json.loads(before).get("default_model", "deepseek")


def test_failed_model_connection_keeps_previous_selection(repl, config):
    original = new_client()
    repl.conversation.model_client = original
    selected = new_client(connected=False)

    with (
        patch("neow.cli.main.create_model_client", return_value=selected),
        patch.object(config, "set_default_model") as default,
    ):
        repl._handle_command(parse_command("/model openai"))

    default.assert_not_called()
    assert repl.conversation.model_client is original
