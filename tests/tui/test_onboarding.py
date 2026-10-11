"""First-run BYOK onboarding and unconfigured-model guards."""

import asyncio
import json
import re
import threading
from html import unescape
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from textual.widgets import Input, OptionList, Static

from neow.core.config import Config, ConfigError
from neow.tui.bridge.controller import ChatController
from neow.tui.bridge.events import TurnFailed
from neow.tui.screens.chat import ChatScreen
from neow.tui.screens.model_editor import ModelEditorScreen
from neow.tui.screens.model_picker import ModelPickerScreen
from neow.tui.widgets.cards import AssistantCard, ErrorCard, UserCard
from tests.tui.conftest import Chunk, FakeConversation, _chat_app

MODEL_NAME = "router"
MODEL_ID = "vendor/chat-model"
SECRET = "onboarding-test-secret"


@pytest.fixture(autouse=True)
def isolate_local_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("ANTHROPIC", "OPENAI", "DEEPSEEK", "ROUTER"):
        monkeypatch.delenv(f"NEOW_{name}_API_KEY", raising=False)


def _entry(key=SECRET):
    return {
        "provider": "openai-compatible",
        "base_url": "https://example.com/v1",
        "model": MODEL_ID,
        "api_key": key,
    }


def _patch_client(monkeypatch, *, connected=True, error=None):
    client = SimpleNamespace(
        model=MODEL_ID,
        config_name=MODEL_NAME,
        validate_connection=Mock(return_value=connected, side_effect=error),
    )
    factory = Mock(return_value=client)
    monkeypatch.setattr("neow.cli.main.create_model_client", factory)
    return client, factory


def _chat_screen(app):
    return next(screen for screen in app.screen_stack if isinstance(screen, ChatScreen))


def _app_text(app):
    return unescape(re.sub(r"<[^>]+>", "", app.export_screenshot())).replace(
        "\u00a0", " "
    )


async def _settle(app, pilot):
    # Let button handlers start workers before waiting for their UI callbacks.
    await pilot.pause()
    await asyncio.wait_for(app.workers.wait_for_complete(), timeout=10)
    await pilot.pause()


async def _open_editor(app, pilot):
    await pilot.pause()
    assert isinstance(app.screen, ModelPickerScreen)
    await pilot.click("#model-add")
    await pilot.pause()
    assert isinstance(app.screen, ModelEditorScreen)
    return app.screen


def _fill_editor(screen, *, key=SECRET):
    for selector, value in (
        ("#model-name", MODEL_NAME),
        ("#model-url", "https://example.com/v1"),
        ("#model-id", MODEL_ID),
        ("#model-key", key),
    ):
        screen.query_one(selector, Input).value = value


async def _select_router(app, pilot):
    picker = app.screen
    assert isinstance(picker, ModelPickerScreen)
    picker.query_one("#model-search", Input).value = MODEL_NAME
    await pilot.pause()
    assert picker.visible_models == [MODEL_NAME]
    picker.query_one(OptionList).focus()
    await pilot.press("enter")
    await _settle(app, pilot)
    return picker


async def test_unconfigured_startup_opens_picker_and_shows_setup_state(tmp_path):
    conversation = FakeConversation(model_client=None)
    config = Config(tmp_path / "config.json")
    app = _chat_app(conversation, config=config, effects="off")

    async with app.run_test(size=(100, 48)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, ModelPickerScreen)
        assert app.screen.query_one("#model-add")
        info = str(_chat_screen(app).query_one("#topbar-info", Static).render())
        assert "unknown" not in info.lower()
        assert "\u914d\u7f6e" in info or "BYOK" in info
        assert conversation.model_client is None
        assert not config.source_path.exists()


@pytest.mark.parametrize("size", [(80, 24), (60, 20)], ids=["standard", "small"])
async def test_first_run_byok_and_save_are_keyboard_accessible_in_small_terminals(
    tmp_path, monkeypatch, size
):
    config = Config(tmp_path / "config.json")
    conversation = FakeConversation(model_client=None)
    client, factory = _patch_client(monkeypatch)
    app = _chat_app(conversation, config=config, effects="off")

    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, ModelPickerScreen)
        for _ in range(8):
            if app.focused is not None and app.focused.id == "model-add":
                break
            await pilot.press("tab")
        assert app.focused.id == "model-add"
        assert 0 <= app.focused.region.y < app.focused.region.bottom <= size[1]
        await pilot.press("enter")
        await pilot.pause()
        editor = app.screen
        assert isinstance(editor, ModelEditorScreen)
        _fill_editor(editor)

        for _ in range(10):
            if app.focused is not None and app.focused.id == "model-save":
                break
            await pilot.press("tab")
        await pilot.pause()
        assert app.focused.id == "model-save"
        assert 0 <= app.focused.region.y < app.focused.region.bottom <= size[1]
        assert 0 <= app.focused.region.x < app.focused.region.right <= size[0]
        await pilot.press("enter")
        await _settle(app, pilot)

        factory.assert_called_once_with(config, MODEL_NAME)
        assert conversation.model_client is client
        assert isinstance(app.screen, ChatScreen)
        assert Config(config.source_path).default_model == MODEL_NAME


async def test_unconfigured_submit_skips_architect_turn_and_history(
    tmp_path, monkeypatch
):
    conversation = FakeConversation(model_client=None)
    config = Config(tmp_path / "config.json")
    app = _chat_app(conversation, config=config, effects="off")

    async with app.run_test(size=(100, 48)) as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        screen = _chat_screen(app)
        screen.commands.architect_mode = True
        plan = Mock(return_value="planned prompt")
        run = Mock()
        monkeypatch.setattr(screen, "_architect_plan", plan)
        monkeypatch.setattr(screen, "_run_turn", run)
        history_before = list(screen.input_dock._history)

        screen.submit_prompt("inspect https://example.com before planning")
        await _settle(app, pilot)

        plan.assert_not_called()
        run.assert_not_called()
        assert conversation.stream_consumed is False
        assert conversation.messages == []
        assert screen._turn_groups == []
        assert screen._turn_number == 0
        assert not list(screen.query(UserCard))
        assert screen.input_dock._history == history_before
        assert screen.queued == []
        assert not screen.busy


async def test_first_save_validates_off_ui_thread_and_persists_default_and_raw_key(
    tmp_path, monkeypatch
):
    path = tmp_path / "config.json"
    config = Config(path)
    conversation = FakeConversation(model_client=None)
    client, factory = _patch_client(monkeypatch)
    ui_thread = threading.get_ident()
    called_threads = []
    stored_when_created = []

    def create(saved_config, name):
        called_threads.append(threading.get_ident())
        stored_when_created.append(json.loads(path.read_text(encoding="utf-8")))
        return client

    def validate():
        called_threads.append(threading.get_ident())
        return True

    factory.side_effect = create
    client.validate_connection.side_effect = validate
    app = _chat_app(conversation, config=config, effects="off")

    async with app.run_test(size=(100, 48)) as pilot:
        editor = await _open_editor(app, pilot)
        _fill_editor(editor)
        assert editor.query_one("#model-key", Input).password
        await pilot.pause()
        assert SECRET not in _app_text(app)
        await pilot.click("#model-save")
        await _settle(app, pilot)

        factory.assert_called_once_with(config, MODEL_NAME)
        client.validate_connection.assert_called_once_with()
        assert called_threads and all(t != ui_thread for t in called_threads)
        assert stored_when_created[0]["models"][MODEL_NAME]["api_key"] == SECRET
        assert conversation.model_client is client
        assert config.default_model == MODEL_NAME
        assert isinstance(app.screen, ChatScreen)
        assert not any(
            isinstance(screen, (ModelEditorScreen, ModelPickerScreen))
            for screen in app.screen_stack
        )
        assert MODEL_ID in str(app.screen.query_one("#topbar-info", Static).render())
        assert SECRET not in _app_text(app)

    raw = json.loads(path.read_text(encoding="utf-8"))
    reloaded = Config(path)
    assert raw["models"][MODEL_NAME]["api_key"] == SECRET
    assert raw["default_model"] == MODEL_NAME
    assert reloaded.default_model == MODEL_NAME
    assert reloaded.stored_model_entry(MODEL_NAME)["api_key"] == SECRET


async def test_first_activation_can_submit_a_successful_chat_turn(
    tmp_path, monkeypatch
):
    config = Config(tmp_path / "config.json")
    conversation = FakeConversation(
        model_client=None,
        script=[Chunk(content_delta="ready to chat"), Chunk(finish_reason="stop")],
    )
    client, _ = _patch_client(monkeypatch)
    app = _chat_app(conversation, config=config, effects="off")

    async with app.run_test(size=(100, 48)) as pilot:
        editor = await _open_editor(app, pilot)
        _fill_editor(editor)
        await pilot.click("#model-save")
        await _settle(app, pilot)
        assert isinstance(app.screen, ChatScreen)
        screen = app.screen
        assert conversation.model_client is client

        screen.submit_prompt("hello after setup")
        await _settle(app, pilot)

        assert conversation.stream_consumed is True
        assert screen._turn_number == 1
        assert len(screen._turn_groups) == 1
        assert [card.body_text() for card in screen.query(UserCard)] == [
            "hello after setup"
        ]
        assert [card.rendered_markdown() for card in screen.query(AssistantCard)] == [
            "ready to chat"
        ]
        assert not list(screen.query(ErrorCard))
        assert not screen.busy
        assert "idle" in str(screen.status_bar.render())


async def test_first_save_waiting_for_validation_keeps_editor_and_disables_actions(
    tmp_path, monkeypatch
):
    config = Config(tmp_path / "config.json")
    conversation = FakeConversation(model_client=None)
    client, _ = _patch_client(monkeypatch)
    entered = threading.Event()
    release = threading.Event()

    def validate():
        entered.set()
        return release.wait(timeout=10)

    client.validate_connection.side_effect = validate
    app = _chat_app(conversation, config=config, effects="off")

    async with app.run_test(size=(100, 48)) as pilot:
        editor = await _open_editor(app, pilot)
        _fill_editor(editor)
        try:
            await pilot.click("#model-save")
            await pilot.pause()
            assert entered.is_set()
            assert app.screen is editor
            assert conversation.model_client is None
            assert editor.query_one("#model-save").disabled
            assert editor.query_one("#model-test").disabled
        finally:
            release.set()
        await _settle(app, pilot)
        assert conversation.model_client is client
        assert isinstance(app.screen, ChatScreen)


async def test_cancelling_pending_first_save_discards_probe_without_switching(
    tmp_path, monkeypatch
):
    config = Config(tmp_path / "config.json")
    original_default = config.default_model
    persist = Mock(wraps=config.set_default_model)
    monkeypatch.setattr(config, "set_default_model", persist)
    conversation = FakeConversation(model_client=None)
    client, factory = _patch_client(monkeypatch)
    entered = threading.Event()
    release = threading.Event()

    def validate():
        entered.set()
        return release.wait(timeout=10)

    client.validate_connection.side_effect = validate
    app = _chat_app(conversation, config=config, effects="off")

    async with app.run_test(size=(100, 48)) as pilot:
        editor = await _open_editor(app, pilot)
        _fill_editor(editor)
        try:
            await pilot.click("#model-save")
            await pilot.pause()
            assert entered.is_set()
            assert conversation.model_client is None
            await pilot.click("#model-cancel")
            await pilot.pause()
            assert editor not in app.screen_stack
            assert isinstance(app.screen, ModelPickerScreen)
        finally:
            release.set()
        await _settle(app, pilot)

        factory.assert_called_once_with(config, MODEL_NAME)
        client.validate_connection.assert_called_once_with()
        persist.assert_not_called()
        assert conversation.model_client is None
        assert config.default_model == original_default
        assert Config(config.source_path).default_model == original_default
        assert isinstance(app.screen, ModelPickerScreen)
        assert not _chat_screen(app)._model_switching


@pytest.mark.parametrize("raises", [False, True], ids=["rejected", "exception"])
async def test_first_save_validation_failure_keeps_editor_and_client_unconfigured(
    tmp_path, monkeypatch, raises
):
    config = Config(tmp_path / "config.json")
    original_default = config.default_model
    conversation = FakeConversation(model_client=None)
    client, factory = _patch_client(
        monkeypatch,
        connected=False,
        error=RuntimeError(f"server echoed {SECRET}") if raises else None,
    )
    app = _chat_app(conversation, config=config, effects="off")

    async with app.run_test(size=(100, 48)) as pilot:
        editor = await _open_editor(app, pilot)
        _fill_editor(editor)
        await pilot.click("#model-save")
        await _settle(app, pilot)

        factory.assert_called_once_with(config, MODEL_NAME)
        client.validate_connection.assert_called_once_with()
        assert app.screen is editor
        assert conversation.model_client is None
        assert config.default_model == original_default
        assert Config(config.source_path).default_model == original_default
        assert config.stored_model_entry(MODEL_NAME)["api_key"] == SECRET
        assert str(editor.query_one("#model-error", Static).render()).strip()
        assert not editor.query_one("#model-save").disabled
        assert not editor.query_one("#model-key", Input).disabled
        assert SECRET not in _app_text(app)


async def test_first_save_can_retry_after_correcting_failed_configuration(
    tmp_path, monkeypatch
):
    config = Config(tmp_path / "config.json")
    conversation = FakeConversation(model_client=None)
    client, factory = _patch_client(monkeypatch, connected=False)
    app = _chat_app(conversation, config=config, effects="off")

    async with app.run_test(size=(100, 48)) as pilot:
        editor = await _open_editor(app, pilot)
        _fill_editor(editor)
        await pilot.click("#model-save")
        await _settle(app, pilot)
        assert app.screen is editor
        assert conversation.model_client is None

        editor.query_one("#model-key", Input).value = "corrected-test-secret"
        client.validate_connection.return_value = True
        # Textual suppresses rapid repeat activation of the same button.
        await pilot.pause(0.25)
        await pilot.click("#model-save")
        await _settle(app, pilot)

        assert factory.call_count == 2
        assert conversation.model_client is client
        assert isinstance(app.screen, ChatScreen)
        assert Config(config.source_path).default_model == MODEL_NAME
        assert (
            config.stored_model_entry(MODEL_NAME)["api_key"] == "corrected-test-secret"
        )


async def test_first_save_default_persistence_failure_does_not_switch(
    tmp_path, monkeypatch
):
    config = Config(tmp_path / "config.json")
    original_default = config.default_model
    conversation = FakeConversation(model_client=None)
    client, factory = _patch_client(monkeypatch)
    persist = Mock(side_effect=ConfigError("Could not save default model"))
    monkeypatch.setattr(config, "set_default_model", persist)
    app = _chat_app(conversation, config=config, effects="off")

    async with app.run_test(size=(100, 48)) as pilot:
        editor = await _open_editor(app, pilot)
        _fill_editor(editor)
        await pilot.click("#model-save")
        await _settle(app, pilot)

        factory.assert_called_once_with(config, MODEL_NAME)
        client.validate_connection.assert_called_once_with()
        persist.assert_called_once_with(MODEL_NAME)
        assert app.screen is editor
        assert conversation.model_client is None
        assert config.default_model == original_default
        assert Config(config.source_path).default_model == original_default
        assert not editor.query_one("#model-save").disabled


async def test_first_save_model_persistence_failure_does_not_validate(
    tmp_path, monkeypatch
):
    config = Config(tmp_path / "config.json")
    conversation = FakeConversation(model_client=None)
    client, factory = _patch_client(monkeypatch)
    monkeypatch.setattr(
        config,
        "save_model",
        Mock(side_effect=ConfigError("Could not save model configuration")),
    )
    app = _chat_app(conversation, config=config, effects="off")

    async with app.run_test(size=(100, 48)) as pilot:
        editor = await _open_editor(app, pilot)
        _fill_editor(editor)
        await pilot.click("#model-save")
        await _settle(app, pilot)

        factory.assert_not_called()
        client.validate_connection.assert_not_called()
        assert app.screen is editor
        assert conversation.model_client is None
        assert MODEL_NAME not in config.models
        assert not config.source_path.exists()


async def test_configured_chat_saving_another_model_does_not_switch(
    tmp_path, monkeypatch
):
    config = Config(tmp_path / "config.json")
    original_default = config.default_model
    conversation = FakeConversation()
    original_client = conversation.model_client
    client, factory = _patch_client(monkeypatch)
    app = _chat_app(conversation, config=config, effects="off")

    async with app.run_test(size=(100, 48)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, ChatScreen)
        app.screen._open_model_picker()
        editor = await _open_editor(app, pilot)
        _fill_editor(editor)
        await pilot.click("#model-save")
        await _settle(app, pilot)

        factory.assert_not_called()
        client.validate_connection.assert_not_called()
        assert conversation.model_client is original_client
        assert config.default_model == original_default
        assert isinstance(app.screen, ModelPickerScreen)
        assert MODEL_NAME in app.screen.models
        assert config.stored_model_entry(MODEL_NAME)["api_key"] == SECRET
        assert Config(config.source_path).default_model == original_default


async def test_picker_success_switches_and_persists_default(tmp_path, monkeypatch):
    config = Config(tmp_path / "config.json")
    config.save_model(MODEL_NAME, _entry())
    conversation = FakeConversation()
    client, factory = _patch_client(monkeypatch)
    app = _chat_app(conversation, config=config, effects="off")

    async with app.run_test(size=(100, 48)) as pilot:
        await pilot.pause()
        app.screen._open_model_picker()
        await pilot.pause()
        await _select_router(app, pilot)

        factory.assert_called_once_with(config, MODEL_NAME)
        client.validate_connection.assert_called_once_with()
        assert isinstance(app.screen, ChatScreen)
        assert conversation.model_client is client
        assert config.default_model == MODEL_NAME
        assert Config(config.source_path).default_model == MODEL_NAME


@pytest.mark.parametrize("persist_fails", [False, True], ids=["connection", "save"])
async def test_picker_failure_stays_open_and_preserves_active_model(
    tmp_path, monkeypatch, persist_fails
):
    config = Config(tmp_path / "config.json")
    config.save_model(MODEL_NAME, _entry())
    original_default = config.default_model
    conversation = FakeConversation()
    original_client = conversation.model_client
    client, factory = _patch_client(monkeypatch, connected=persist_fails)
    if persist_fails:
        monkeypatch.setattr(
            config,
            "set_default_model",
            Mock(side_effect=ConfigError("Could not save default model")),
        )
    app = _chat_app(conversation, config=config, effects="off")

    async with app.run_test(size=(100, 48)) as pilot:
        await pilot.pause()
        app.screen._open_model_picker()
        await pilot.pause()
        picker = await _select_router(app, pilot)

        factory.assert_called_once_with(config, MODEL_NAME)
        client.validate_connection.assert_called_once_with()
        assert app.screen is picker
        assert conversation.model_client is original_client
        assert config.default_model == original_default
        assert Config(config.source_path).default_model == original_default
        assert str(picker.query_one("#model-message", Static).render()).strip()
        assert SECRET not in _app_text(app)


async def test_named_model_command_switches_asynchronously_and_persists_default(
    tmp_path, monkeypatch
):
    config = Config(tmp_path / "config.json")
    config.save_model(MODEL_NAME, _entry())
    original_default = config.default_model
    conversation = FakeConversation()
    original_client = conversation.model_client
    client, factory = _patch_client(monkeypatch)
    ui_thread = threading.get_ident()
    called_threads = []

    def create(saved_config, name):
        called_threads.append(threading.get_ident())
        return client

    def validate():
        called_threads.append(threading.get_ident())
        return True

    factory.side_effect = create
    client.validate_connection.side_effect = validate
    app = _chat_app(conversation, config=config, effects="off")

    async with app.run_test(size=(100, 48)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ChatScreen)
        screen.dispatch_command(f"/model {MODEL_NAME}")
        assert screen._model_switching
        assert conversation.model_client is original_client
        assert config.default_model == original_default
        assert app.screen is screen
        await _settle(app, pilot)

        factory.assert_called_once_with(config, MODEL_NAME)
        client.validate_connection.assert_called_once_with()
        assert called_threads and all(t != ui_thread for t in called_threads)
        assert conversation.model_client is client
        assert config.default_model == MODEL_NAME
        assert Config(config.source_path).default_model == MODEL_NAME
        assert app.screen is screen
        assert not screen._model_switching


@pytest.mark.parametrize("failure", ["connection", "exception", "save"])
async def test_named_model_command_failure_preserves_active_model_and_default(
    tmp_path, monkeypatch, failure
):
    config = Config(tmp_path / "config.json")
    config.save_model(MODEL_NAME, _entry())
    original_default = config.default_model
    conversation = FakeConversation()
    original_client = conversation.model_client
    client, factory = _patch_client(
        monkeypatch,
        connected=failure == "save",
        error=(
            RuntimeError(f"server echoed {SECRET}") if failure == "exception" else None
        ),
    )
    persist = Mock(wraps=config.set_default_model)
    if failure == "save":
        persist.side_effect = ConfigError("Could not save default model")
    monkeypatch.setattr(config, "set_default_model", persist)
    app = _chat_app(conversation, config=config, effects="off")

    async with app.run_test(size=(100, 48)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ChatScreen)
        screen.dispatch_command(f"/model {MODEL_NAME}")
        assert screen._model_switching
        await _settle(app, pilot)

        factory.assert_called_once_with(config, MODEL_NAME)
        client.validate_connection.assert_called_once_with()
        if failure == "save":
            persist.assert_called_once_with(MODEL_NAME)
        else:
            persist.assert_not_called()
        assert app.screen is screen
        assert conversation.model_client is original_client
        assert config.default_model == original_default
        assert Config(config.source_path).default_model == original_default
        assert not screen._model_switching
        assert not screen.busy
        assert list(screen.query(ErrorCard))
        assert SECRET not in _app_text(app)


def test_unconfigured_controller_fails_before_web_plugins_or_stream():
    conversation = FakeConversation(
        model_client=None, script=[Chunk(content_delta="must not be consumed")]
    )
    events = []
    fetcher = Mock()
    event_bus = Mock()
    tracker = Mock()
    controller = ChatController(
        conversation,
        event_callback=events.append,
        web_fetcher=fetcher,
        event_bus=event_bus,
        token_tracker=tracker,
    )

    controller.run_turn("read https://example.com before answering")

    assert len(events) == 1
    assert isinstance(events[0], TurnFailed)
    assert events[0].message.strip()
    fetcher.fetch.assert_not_called()
    event_bus.emit.assert_not_called()
    tracker.check_max_tokens.assert_not_called()
    assert conversation.stream_consumed is False
    assert conversation.messages == []
    assert conversation.added_web == []
    assert conversation.on_cancel is None
    assert not controller.busy


@pytest.mark.parametrize("connected", [True, False], ids=["success", "failure"])
async def test_late_connection_test_cannot_override_pending_activation(
    tmp_path, monkeypatch, connected
):
    config = Config(tmp_path / "config.json")
    conversation = FakeConversation(model_client=None)
    app = _chat_app(conversation, config=config, effects="off")

    async with app.run_test(size=(100, 48)) as pilot:
        editor = await _open_editor(app, pilot)
        _fill_editor(editor)
        run_test = Mock()
        monkeypatch.setattr(editor, "run_worker", run_test)
        editor._test_connection(MODEL_NAME, _entry())
        assert editor._test_pending
        run_test.assert_called_once()

        activation_message = "activation connection probe in progress"
        editor.set_activation_pending(True, activation_message)
        editor._tested(connected)

        assert not editor._test_pending
        assert editor._activation_pending
        assert editor.query_one("#model-test").disabled
        assert editor.query_one("#model-save").disabled
        assert editor.query_one("#model-key", Input).disabled
        assert str(editor.query_one("#model-error", Static).render()) == (
            activation_message
        )
        assert conversation.model_client is None

        editor.set_activation_pending(False, "activation failure; retry")
        assert not editor.query_one("#model-test").disabled
        assert not editor.query_one("#model-save").disabled
        assert not editor.query_one("#model-key", Input).disabled
