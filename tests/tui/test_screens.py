"""Feature screen and sidebar tests (plan task 14)."""

import re
from html import unescape

from textual.containers import VerticalScroll
from textual.widgets import Input, Tree
from neow.core.config import Config
from neow.tui.screens.approval_mode import ApprovalModeScreen
from neow.tui.screens.chat import ChatScreen
from neow.tui.screens.clear_confirm import ClearConfirmScreen
from neow.tui.screens.commit_modal import CommitModalScreen
from neow.tui.screens.compaction_picker import CompactionPickerScreen
from neow.tui.screens.context_drop import ContextDropScreen
from neow.tui.screens.context_list import ContextListScreen
from neow.tui.screens.cost import CostScreen
from neow.tui.screens.diff_view import DiffScreen
from neow.tui.screens.effort_picker import EffortPickerScreen
from neow.tui.screens.exit_confirm import ExitConfirmScreen
from neow.tui.screens.export_picker import ExportPickerScreen
from neow.tui.screens.file_picker import FilePickerScreen
from neow.tui.screens.goal_modal import GoalModalScreen
from neow.tui.screens.help import HelpScreen
from neow.tui.screens.image_picker import ImagePickerScreen
from neow.tui.screens.imgdiff_modal import ImgDiffModalScreen
from neow.tui.screens.init_modal import InitModalScreen
from neow.tui.screens.lint_modal import LintModalScreen
from neow.tui.screens.mcp_manager import McpManagerScreen
from neow.tui.screens.memory import MemoryScreen
from neow.tui.screens.mode_picker import ModePickerScreen
from neow.tui.screens.model_editor import ModelEditorScreen
from neow.tui.screens.model_picker import ModelPickerScreen
from neow.tui.screens.rewind_picker import RewindPickerScreen
from neow.tui.screens.session_picker import SessionPickerScreen
from neow.tui.screens.session_save import SessionSaveScreen
from neow.tui.screens.test_modal import TestModalScreen
from neow.tui.screens.thinking_detail import ThinkingDetailScreen
from neow.tui.screens.thinking_picker import ThinkingPickerScreen
from neow.tui.screens.tree import SessionTreeScreen
from neow.tui.screens.undo_confirm import UndoConfirmScreen
from neow.tui.screens.verbosity_picker import VerbosityPickerScreen
from neow.tui.screens.web_fetch import WebFetchScreen
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


async def test_effort_picker_renders_levels_and_selects():
    selected = []
    app = _screen_app(
        EffortPickerScreen(
            current="off",
            model_name="test-model",
            on_select=selected.append,
        )
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        text = _app_text(app)
        assert "off" in text
        assert "low" in text
        assert "medium" in text
        assert "high" in text
        assert "当前" in text
        await pilot.press("down", "enter")
        await pilot.pause()
        assert selected == ["low"]


async def test_chat_screen_effort_command_flow():
    conv = FakeConversation()
    chat_app = _chat_app(conv, config=Config())
    async with chat_app.run_test() as pilot:
        await pilot.pause()
        chat = chat_app.screen
        assert isinstance(chat, ChatScreen)
        chat.dispatch_command("/effort")
        await pilot.pause()
        assert isinstance(chat_app.screen, EffortPickerScreen)
        await pilot.press("down", "enter")
        await pilot.pause()
        assert isinstance(chat_app.screen, ChatScreen)
        assert conv.model_client.effort == "low"


async def test_approval_mode_picker_renders_and_selects():
    selected = []
    app = _screen_app(ApprovalModeScreen(current="write", on_select=selected.append))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "write" in _app_text(app)
        await pilot.press("enter")
        await pilot.pause()
        assert selected == ["write"]


async def test_mode_picker_renders_and_selects():
    selected = []
    app = _screen_app(ModePickerScreen(current="code", on_select=selected.append))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "code" in _app_text(app)
        await pilot.press("down", "enter")
        await pilot.pause()
        assert selected == ["architect"]


async def test_verbosity_picker_renders_and_selects():
    selected = []
    app = _screen_app(VerbosityPickerScreen(current=False, on_select=selected.append))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "off" in _app_text(app)
        await pilot.press("down", "enter")
        await pilot.pause()
        assert selected == [True]


async def test_clear_confirm_screen_runs_callback():
    confirmed = []
    app = _screen_app(ClearConfirmScreen(on_confirm=lambda: confirmed.append(True)))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#confirm-btn")
        await pilot.pause()
        assert confirmed == [True]


async def test_undo_confirm_screen_runs_callback():
    confirmed = []
    app = _screen_app(UndoConfirmScreen(on_confirm=lambda: confirmed.append(True)))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#confirm-btn")
        await pilot.pause()
        assert confirmed == [True]


async def test_exit_confirm_screen_runs_callback():
    exited = []
    app = _screen_app(ExitConfirmScreen(on_exit=exited.append))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#direct-exit-btn")
        await pilot.pause()
        assert exited == [False]


async def test_session_save_screen_submits_name():
    saved = []
    app = _screen_app(SessionSaveScreen(default_name="test-sess", on_save=saved.append))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert saved == ["test-sess"]


async def test_web_fetch_screen_submits_url():
    fetched = []
    app = _screen_app(WebFetchScreen(on_fetch=fetched.append))
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one(Input).value = "https://example.com"
        await pilot.press("enter")
        await pilot.pause()
        assert fetched == ["https://example.com"]


async def test_compaction_picker_selects_strategy():
    compacted = []
    app = _screen_app(CompactionPickerScreen(on_select=compacted.append))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert compacted == ["full"]


async def test_export_picker_selects_format():
    exported = []
    app = _screen_app(ExportPickerScreen(on_select=exported.append))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert exported == ["markdown"]


async def test_context_drop_screen_drops_file():
    dropped = []
    app = _screen_app(ContextDropScreen(files=["a.py", "b.py"], on_drop=dropped.append))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert dropped == ["a.py"]


async def test_context_list_screen_renders():
    app = _screen_app(ContextListScreen(files=["main.py"]))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "main.py" in _app_text(app)


async def test_file_picker_screen_selects_file(tmp_path):
    (tmp_path / "hello.py").write_text("print('hi')")
    selected = []
    app = _screen_app(
        FilePickerScreen(workspace_root=tmp_path, on_select=selected.append)
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert selected == ["hello.py"]


async def test_image_picker_screen_selects_image(tmp_path):
    (tmp_path / "shot.png").write_text("fake png")
    selected = []
    app = _screen_app(
        ImagePickerScreen(workspace_root=tmp_path, on_select=selected.append)
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert selected == ["shot.png"]


async def test_imgdiff_modal_submits_images():
    compared = []
    app = _screen_app(
        ImgDiffModalScreen(on_compare=lambda a, b: compared.append((a, b)))
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#img1-input", Input).value = "a.png"
        app.screen.query_one("#img2-input", Input).value = "b.png"
        await pilot.click("#compare-btn")
        await pilot.pause()
        assert compared == [("a.png", "b.png")]


async def test_commit_modal_submits_message():
    committed = []
    app = _screen_app(
        CommitModalScreen(changed_files_summary="2 files", on_commit=committed.append)
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one(Input).value = "feat: new feature"
        await pilot.click("#commit-btn")
        await pilot.pause()
        assert committed == ["feat: new feature"]


async def test_lint_modal_screen_renders():
    fixed = []
    app = _screen_app(
        LintModalScreen(
            command="flake8", output="all ok", on_auto_fix=lambda: fixed.append(True)
        )
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "all ok" in _app_text(app)
        await pilot.click("#fix-btn")
        await pilot.pause()
        assert fixed == [True]


async def test_test_modal_screen_renders():
    fixed = []
    app = _screen_app(
        TestModalScreen(
            command="pytest",
            output="all passed",
            on_auto_fix=lambda: fixed.append(True),
        )
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "all passed" in _app_text(app)
        await pilot.click("#fix-btn")
        await pilot.pause()
        assert fixed == [True]


async def test_init_modal_screen_generates():
    generated = []
    app = _screen_app(
        InitModalScreen(
            preview_text="# AI rules", on_generate=lambda: generated.append(True)
        )
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "AI rules" in _app_text(app)
        await pilot.click("#gen-btn")
        await pilot.pause()
        assert generated == [True]


async def test_memory_screen_adds_note():
    notes = []
    app = _screen_app(MemoryScreen(notes=["Project rule 1"], on_add_note=notes.append))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "Project rule 1" in _app_text(app)
        app.screen.query_one(Input).value = "Project rule 2"
        await pilot.click("#add-note-btn")
        await pilot.pause()
        assert notes == ["Project rule 2"]


async def test_mcp_manager_screen_renders():
    app = _screen_app(McpManagerScreen(servers={"github": {}}, tools=["get_issue"]))
    async with app.run_test() as pilot:
        await pilot.pause()
        text = _app_text(app)
        assert "github" in text
        assert "get_issue" in text


async def test_rewind_picker_selects_turn():
    rewound = []
    app = _screen_app(
        RewindPickerScreen(
            checkpoints=[{"turn": 2, "prompt": "rewind test", "files": {}}],
            on_rewind=rewound.append,
        )
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert rewound == [2]


async def test_thinking_detail_screen_renders():
    app = _screen_app(ThinkingDetailScreen(reasoning="Deep reasoning trace text"))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "Deep reasoning trace text" in _app_text(app)


async def test_thinking_picker_screen_selects_option():
    selected = []
    screen = ThinkingPickerScreen(current=True, on_select=selected.append)
    app = _screen_app(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("down", "enter")
        await pilot.pause()
        assert selected == ["off"]

    selected_view = []
    screen2 = ThinkingPickerScreen(current=True, on_select=selected_view.append)
    app2 = _screen_app(screen2)
    async with app2.run_test() as pilot2:
        await pilot2.pause()
        await pilot2.press("down", "down", "enter")
        await pilot2.pause()
        assert selected_view == ["view"]


async def test_chat_screen_interactive_commands_push_modals():
    conv = FakeConversation()
    conv.context_files = ["x.py"]
    chat_app = _chat_app(conv, config=Config())
    async with chat_app.run_test() as pilot:
        await pilot.pause()
        chat = chat_app.screen
        assert isinstance(chat, ChatScreen)

        modal_cmds = [
            ("/approval", ApprovalModeScreen),
            ("/mode", ModePickerScreen),
            ("/save", SessionSaveScreen),
            ("/web", WebFetchScreen),
            ("/compact", CompactionPickerScreen),
            ("/export", ExportPickerScreen),
            ("/commit", CommitModalScreen),
            ("/memory", MemoryScreen),
            ("/mcp", McpManagerScreen),
            ("/rewind", RewindPickerScreen),
            ("/thinking", ThinkingPickerScreen),
            ("/ls", ContextListScreen),
            ("/add", FilePickerScreen),
            ("/drop", ContextDropScreen),
            ("/image", ImagePickerScreen),
            ("/imgdiff", ImgDiffModalScreen),
            ("/goal", GoalModalScreen),
        ]

        for cmd, screen_cls in modal_cmds:
            chat.dispatch_command(cmd)
            await pilot.pause()
            curr = chat_app.screen
            assert isinstance(
                curr, screen_cls
            ), f"Expected {screen_cls.__name__} for {cmd}, got {type(curr).__name__}"
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(chat_app.screen, ChatScreen)

        # Direct execution commands that do NOT open modals
        chat.dispatch_command("/architect")
        await pilot.pause()
        assert isinstance(chat_app.screen, ChatScreen)
        assert conv.architect_mode is True

        chat.dispatch_command("/code")
        await pilot.pause()
        assert isinstance(chat_app.screen, ChatScreen)
        assert conv.architect_mode is False

        chat.dispatch_command("/verbose")
        await pilot.pause()
        assert isinstance(chat_app.screen, ChatScreen)
        assert conv.verbose is True

        chat.dispatch_command("/clear")
        await pilot.pause()
        assert isinstance(chat_app.screen, ChatScreen)


async def test_chat_screen_exit_command_exits_directly_without_modal():
    conv = FakeConversation()
    chat_app = _chat_app(conv)
    async with chat_app.run_test() as pilot:
        await pilot.pause()
        chat = chat_app.screen
        assert isinstance(chat, ChatScreen)
        chat.dispatch_command("/exit")
        await pilot.pause()
        assert chat_app._exit is True


async def test_goal_modal_screen_starts_and_stops():
    from neow.core.goal import GoalState

    started = []
    stopped = []
    app = _screen_app(
        GoalModalScreen(
            active_goal=GoalState(goal="old goal", active=True, current_round=2),
            on_start=started.append,
            on_stop=lambda: stopped.append(True),
        )
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "old goal" in _app_text(app)
        app.screen.query_one("#goal-input", Input).value = "new goal"
        await pilot.click("#start-goal-btn")
        await pilot.pause()
        assert started == ["new goal"]

    app2 = _screen_app(
        GoalModalScreen(
            active_goal=GoalState(goal="running goal", active=True, current_round=1),
            on_start=started.append,
            on_stop=lambda: stopped.append(True),
        )
    )
    async with app2.run_test() as pilot2:
        await pilot2.pause()
        await pilot2.click("#stop-goal-btn")
        await pilot2.pause()
        assert stopped == [True]


async def test_model_picker_buttons_remain_visible_with_many_magpie_models(tmp_path):
    config = Config(tmp_path / "config.json")
    for idx in range(50):
        config.models[f"magpie/cursor/model-{idx}"] = {
            "provider": "openai-compatible",
            "model": f"cursor/model-{idx}",
            "base_url": "http://127.0.0.1:3425/v1",
            "source": "magpie",
            "display_name": f"Model {idx} · Cursor",
            "api_key": "magpie",
        }
    app = _chat_app(FakeConversation(), config=config)
    async with app.run_test(size=(100, 26)) as pilot:
        app.screen._open_model_picker()
        await pilot.pause()
        picker = app.screen
        for btn_id in ("#model-add", "#model-edit", "#model-sync", "#model-delete"):
            btn = picker.query_one(btn_id)
            assert (
                0 <= btn.region.y < btn.region.bottom <= 26
            ), f"{btn_id} clipped out of viewport: {btn.region}"
        await pilot.click("#model-add")
        await pilot.pause()
        editor = app.screen
        preset = editor.query_one("#model-preset")
        assert 0 <= preset.region.y < preset.region.bottom <= 26
