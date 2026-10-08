"""Feature screen and sidebar tests (plan task 14)."""

import re

from textual.containers import VerticalScroll
from textual.widgets import Tree
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
    return re.sub(r"<[^>]+>", "", svg)


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
