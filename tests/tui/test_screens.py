"""Feature screen and sidebar tests (plan task 14)."""

import re
from html import unescape

from textual.containers import VerticalScroll
from textual.widgets import Input, Tree
from neow.core.config import Config
from neow.tui.screens.model_editor import ModelEditorScreen
from neow.tui.screens.chat import ChatScreen
from neow.tui.screens.cost import CostScreen
from neow.tui.screens.diff_view import DiffScreen
from neow.tui.screens.help import HelpScreen
from neow.tui.screens.model_picker import ModelPickerScreen
from neow.tui.screens.session_picker import SessionPickerScreen
from neow.tui.screens.tree import SessionTreeScreen
from tests.tui.conftest import FakeConversation, _chat_app, _screen_app


def _app_text(app) -> str:
    svg = app.export_screenshot()
    return unescape(re.sub(r"<[^>]+>", "", svg)).replace("\u00a0", " ")


async def test_help_screen_lists_all_commands():
    app = _screen_app(HelpScreen())
    async with app.run_test() as pilot:
        await pilot.pause()
        text = _app_text(app)
        for command in ["/help", "/model", "/diff", "/tree", "/approval"]:
            assert command in text


async def test_model_picker_switches_via_callback():
    switched = []
    app = _screen_app(
        ModelPickerScreen(models=["deepseek", "openai"], on_select=switched.append)
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("down", "enter")
        await pilot.pause()
        assert switched == ["openai"]


async def test_model_picker_labels_shown_and_selection_returns_name():
    switched = []
    app = _screen_app(
        ModelPickerScreen(
            models=["openrouter"],
            labels={"openrouter": "openrouter (openai-compatible)"},
            on_select=switched.append,
        )
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "openai-compatible" in _app_text(app)
        await pilot.press("enter")
        await pilot.pause()
        assert switched == ["openrouter"]


async def test_model_picker_search_maps_selection_to_filtered_name():
    switched = []
    app = _screen_app(
        ModelPickerScreen(
            models=["a", "b"], labels={"b": "Magpie GPT"}, on_select=switched.append
        )
    )
    async with app.run_test() as pilot:
        app.screen.query_one(Input).value = "GPT"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert switched == ["b"]


async def test_byok_editor_saves_and_masks_key(tmp_path):
    config = Config(tmp_path / "config.json")
    saved = []
    app = _screen_app(
        ModelEditorScreen(config=config, on_saved=lambda: saved.append(True))
    )
    async with app.run_test(size=(100, 48)) as pilot:
        screen = app.screen
        screen.query_one("#model-name", Input).value = "router"
        screen.query_one("#model-url", Input).value = "https://example.com/v1"
        screen.query_one("#model-id", Input).value = "vendor/m"
        screen.query_one("#model-key", Input).value = "hidden-secret"
        assert screen.query_one("#model-key", Input).password
        assert "hidden-secret" not in _app_text(app)
        await pilot.click("#model-save")
        await pilot.pause()
        assert saved == [True]
        assert config.models["router"]["model"] == "vendor/m"


async def test_byok_edit_keeps_stored_key_hidden(tmp_path):
    config = Config(tmp_path / "config.json")
    config.save_model(
        "router",
        {
            "provider": "openai-compatible",
            "model": "m",
            "base_url": "https://example.com/v1",
            "api_key": "stored-secret",
        },
    )
    app = _screen_app(
        ModelEditorScreen(config=config, name="router", on_saved=lambda: None)
    )
    async with app.run_test(size=(100, 48)) as pilot:
        assert app.screen.query_one("#model-key", Input).value == ""
        assert "stored-secret" not in _app_text(app)
        await pilot.click("#model-save")
        assert config.models["router"]["api_key"] == "stored-secret"


async def test_model_editor_scrolls_in_small_terminal(tmp_path):
    config = Config(tmp_path / "config.json")
    app = _chat_app(FakeConversation(), config=config)
    async with app.run_test(size=(60, 20)) as pilot:
        app.screen._open_model_editor()
        await pilot.pause()
        screen = app.screen
        for selector, value in [
            ("#model-name", "small"),
            ("#model-url", "http://localhost:1234/v1"),
            ("#model-id", "m"),
            ("#model-key", "local"),
        ]:
            screen.query_one(selector, Input).value = value
        await pilot.press("tab", "tab", "tab", "tab", "tab", "tab")
        await pilot.pause()
        assert app.focused.id == "model-save"
        assert app.focused.region.bottom <= 20
        await pilot.press("enter")
        await pilot.pause()
        assert "small" in config.models


async def test_magpie_sync_refreshes_open_picker(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    config = Config(tmp_path / "config.json")
    response = MagicMock()
    response.json.return_value = {
        "data": [{"id": "vendor/m", "display_name": "Gateway model"}]
    }
    monkeypatch.setattr(
        "neow.models.management.requests.get", lambda *args, **kwargs: response
    )
    app = _chat_app(FakeConversation(), config=config)
    async with app.run_test(size=(100, 40)) as pilot:
        app.screen._open_model_picker()
        await pilot.pause()
        await pilot.click("#model-sync")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "magpie/vendor/m" in app.screen.models
        assert "Gateway model" in _app_text(app)


async def test_session_picker_lists_sessions():
    sessions = [
        {
            "name": "s1",
            "message_count": 3,
            "model": "m",
            "created_at": "2026-10-07",
        }
    ]
    app = _screen_app(
        SessionPickerScreen(sessions=sessions, on_select=lambda name: None)
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "s1" in _app_text(app)


async def test_tree_screen_renders_nodes():
    tree = {
        "a": {
            "parentId": None,
            "children": ["b"],
            "role": "user",
            "content_preview": "hi",
        },
        "b": {
            "parentId": "a",
            "children": [],
            "role": "assistant",
            "content_preview": "there",
        },
    }
    app = _screen_app(
        SessionTreeScreen(tree=tree, leaf_id="b", on_goto=lambda node: None)
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "hi" in _app_text(app)


async def test_diff_screen_shows_diff_and_binds_commit():
    app = _screen_app(
        DiffScreen(
            diff_text="+added\n-removed", on_commit=lambda: None, on_undo=lambda: None
        )
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "added" in _app_text(app)
        await pilot.press("c")
        await pilot.pause()
        assert app.screen.committed


async def test_diff_screen_renders_markup_like_text():
    text = '{"type": "reasoning_start"}\n+ [bold]literal[/bold]'
    app = _screen_app(
        DiffScreen(diff_text=text, on_commit=lambda: None, on_undo=lambda: None)
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "reasoning_start" in _app_text(app)


async def test_cost_screen_shows_summary():
    app = _screen_app(CostScreen(summary="deepseek 1.2k in / 3.4k out $0.0042"))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "$0.0042" in _app_text(app)


async def test_sidebar_tabs_cycle_and_refresh():
    app = _chat_app(FakeConversation(script=[]))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ChatScreen)
        await pilot.press("ctrl+b")
        await pilot.pause()
        assert screen.sidebar_visible
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert screen.sidebar_tab == "todos"
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert screen.sidebar_tab == "tree"
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert screen.sidebar_tab == "git"


async def test_help_scrolls_on_small_terminal():
    app = _screen_app(HelpScreen())
    async with app.run_test(size=(60, 16)) as pilot:
        await pilot.press("pagedown")
        await pilot.pause()
        assert app.screen.query_one(VerticalScroll).scroll_y > 0


async def test_tree_branch_uses_highlighted_node():
    branched = []
    app = _screen_app(
        SessionTreeScreen(
            tree={
                "node1": {
                    "parentId": None,
                    "children": [],
                    "role": "user",
                    "content_preview": "[bold]literal",
                }
            },
            on_branch=branched.append,
        )
    )
    async with app.run_test() as pilot:
        tree = app.screen.query_one(Tree)
        tree.select_node(tree.root.children[0])
        await pilot.press("b")
        assert branched == ["node1"]
