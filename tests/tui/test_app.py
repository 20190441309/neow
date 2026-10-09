"""App shell and chat integration tests (plan tasks 2 and 11)."""

from types import SimpleNamespace

import pytest

from neow.tui.app import resolve_effects
from neow.tui.screens.approval import ApprovalModal
from neow.tui.screens.chat import ChatScreen
from neow.tui.widgets.cards import AssistantCard, CardBase, UserCard
from neow.tui.widgets.cards.system import CompactionCard
from neow.tui.widgets.logo import NeowLogo
from tests.tui.conftest import Chunk, FakeConversation, _chat_app, _host

CARD_SCRIPT = [
    Chunk(progress={"type": "reasoning_start"}),
    Chunk(reasoning_delta="think"),
    Chunk(progress={"type": "reasoning_end"}),
    Chunk(content_delta="hello"),
    Chunk(
        progress={
            "type": "tool_start",
            "name": "read_file",
            "args": {"path": "a.py"},
        }
    ),
    Chunk(progress={"type": "tool_end", "name": "read_file", "result": "ok"}),
    Chunk(content_delta=" world"),
    Chunk(finish_reason="stop"),
]


async def test_app_mounts():
    app = _chat_app(FakeConversation(script=[]))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.screen.query_one("#topbar")
        assert app.screen.query_one("#statusbar")
        assert isinstance(app.screen, ChatScreen)


async def test_narrow_resize_no_crash():
    app = _chat_app(FakeConversation(script=[]))
    async with app.run_test(size=(60, 20)) as pilot:
        await pilot.pause()
        await pilot.resize_terminal(58, 18)
        await pilot.pause()
        assert app.screen.query_one("#inputdock")


async def test_submit_creates_cards_in_order():
    app = _chat_app(FakeConversation(script=CARD_SCRIPT))
    async with app.run_test(size=(120, 40)) as pilot:
        screen = app.screen
        assert isinstance(screen, ChatScreen)
        screen.submit_prompt("hi")
        await pilot.pause(0.5)
        cards = [type(card).__name__ for card in screen.query(CardBase)]
        assert cards == [
            "UserCard",
            "ThinkingCard",
            "AssistantCard",
            "ToolCard",
            "AssistantCard",
        ]


async def test_queue_drains_after_turn():
    script = [Chunk(content_delta="ok"), Chunk(finish_reason="stop")]
    app = _chat_app(FakeConversation(script=script))
    async with app.run_test(size=(120, 40)) as pilot:
        screen = app.screen
        assert isinstance(screen, ChatScreen)
        screen.submit_prompt("first")
        screen.submit_prompt("second")
        screen.submit_prompt("third")
        assert screen.queued == ["second", "third"]
        await pilot.pause(0.8)
        assert screen.queued == []
        assert [card.body_text() for card in screen.query(UserCard)] == [
            "first",
            "second",
            "third",
        ]


async def test_cancel_then_submit_again():
    conv = FakeConversation(script=[Chunk(content_delta="a"), "CANCEL"])
    app = _chat_app(conv)
    async with app.run_test(size=(120, 40)) as pilot:
        screen = app.screen
        assert isinstance(screen, ChatScreen)
        screen.submit_prompt("a")
        await pilot.pause(0.2)
        screen.cancel_turn()
        await pilot.pause(0.3)
        screen.submit_prompt("b")
        await pilot.pause(0.4)
        assert not screen.busy


async def test_exit_with_pending_approval():
    app = _chat_app(FakeConversation(script=[]))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(
            ApprovalModal(
                tool="execute_command",
                params={"command": "npm test"},
                reason="exec",
            )
        )
        await pilot.pause(0.1)
        app.exit()
    # Reaching this point (no hang, no exception) is the assertion.


async def test_effects_off_disables_logo_timer():
    app = _chat_app(FakeConversation(script=[]), effects="off")
    async with app.run_test() as pilot:
        await pilot.pause()
        logo = app.screen.query_one(NeowLogo)
        assert logo._timer is None


async def test_logo_skips_on_any_key():
    app = _chat_app(FakeConversation(script=[]), effects="full")
    async with app.run_test() as pilot:
        await pilot.pause()
        logo = app.screen.query_one(NeowLogo)
        logo.start_splash()
        assert logo._timer is not None
        await pilot.press("x")
        await pilot.pause()
        assert logo.collapsed_splash
        assert logo._timer is None


def test_effect_mode_from_config_and_env(monkeypatch):
    monkeypatch.setenv("TEXTUAL_ANIMATIONS", "none")
    assert resolve_effects("full") == "off"
    assert resolve_effects("subtle", env_none=False) == "subtle"
    monkeypatch.delenv("TEXTUAL_ANIMATIONS")
    assert resolve_effects("warp9") == "full"
    assert resolve_effects("off") == "off"


async def test_full_effects_play_card_entrance():
    card = UserCard("hi", number=1, timestamp="t")
    async with _host(card) as pilot:
        card.play_entrance()
        assert card.styles.opacity == 0.0
        await pilot.pause(0.4)
        assert card.styles.opacity == 1.0


async def test_exit_saves_session():
    saved = []
    manager = SimpleNamespace(save=lambda conversation: saved.append(True) or "s")
    app = _chat_app(FakeConversation(script=[]), session_manager=manager)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.exit()
    assert saved


async def test_sidebar_default_config_shows_sidebar():
    config = SimpleNamespace(tui={"sidebar_default": True})
    app = _chat_app(FakeConversation(script=[]), config=config)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.screen.sidebar_visible


async def test_f1_opens_help():
    from neow.tui.screens.help import HelpScreen

    app = _chat_app(FakeConversation(script=[]))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("f1")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)


async def test_command_palette_lists_slash_commands():
    app = _chat_app(FakeConversation(script=[]))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        commands = list(app.get_system_commands(app.screen))
        assert "/help" in [command.title for command in commands]


async def test_compact_command_renders_compaction_card():
    app = _chat_app(FakeConversation(script=[]))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.dispatch_command("/compact")
        await pilot.pause()
        cards = list(screen.query(CompactionCard))
        assert cards and cards[-1].collapsed
        assert "Compacted" in cards[-1].title_text()


async def test_ctrl_y_copies_last_code_block():
    script = [
        Chunk(content_delta="first\n```python\nprint(1)\n```\n"),
        Chunk(content_delta="second\n```bash\necho hi\n```"),
        Chunk(finish_reason="stop"),
    ]
    app = _chat_app(FakeConversation(script=script))
    copied = []
    app.copy_to_clipboard = lambda text: copied.append(text)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.screen.submit_prompt("hi")
        await pilot.pause(0.5)
        await pilot.press("ctrl+y")
        await pilot.pause(0.1)
        assert copied == ["echo hi"]


async def test_ctrl_y_without_code_shows_notice():
    script = [Chunk(content_delta="no code here"), Chunk(finish_reason="stop")]
    app = _chat_app(FakeConversation(script=script))
    copied = []
    notices = []
    app.copy_to_clipboard = lambda text: copied.append(text)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.notify = lambda *args, **kwargs: notices.append((args, kwargs))
        screen.submit_prompt("hi")
        await pilot.pause(0.5)
        await pilot.press("ctrl+y")
        await pilot.pause(0.1)
        assert copied == [] and notices


async def test_split_assistant_segments_finish_their_cursors():
    script = [
        Chunk(content_delta="one"),
        Chunk(
            progress={
                "type": "tool_start",
                "name": "read_file",
                "args": {"path": "a.py"},
            }
        ),
        Chunk(progress={"type": "tool_end", "name": "read_file", "result": "ok"}),
        Chunk(content_delta="two"),
        Chunk(finish_reason="stop"),
    ]
    app = _chat_app(FakeConversation(script=script))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.submit_prompt("hi")
        await pilot.pause(0.5)
        cards = list(screen.query(AssistantCard))
        assert len(cards) == 2
        assert all(not card.cursor_visible for card in cards)


@pytest.mark.parametrize("size", [(120, 40), (80, 24), (60, 16), (40, 12)])
async def test_completion_and_multiline_editor_stay_inside_screen(size):
    app = _chat_app(effects="off")
    async with app.run_test(size=size) as pilot:
        screen = app.screen
        for text in ("/", "line\n" * 10 + "@"):
            screen.input_dock.set_text(text)
            await pilot.pause()
            for selector in ("PromptArea", "#statusbar", "#completions"):
                widget = screen.query_one(selector)
                if widget.display:
                    assert widget.region.y >= 0
                    assert widget.region.bottom <= size[1]
            assert screen.scroll_y == 0


async def test_topbar_model_visible_and_status_initialized():
    app = _chat_app(effects="off")
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        info = app.screen.query_one("#topbar-info")
        assert info.region.width > 20
        assert info.region.right <= 80
        assert "fake" in str(info.render())
        assert "idle" in str(app.screen.status_bar.render())


async def test_tab_completes_in_app_without_opening_sidebar():
    app = _chat_app(effects="off")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press(*"/mo", "tab")
        assert app.screen.input_dock.text() == "/model "
        assert not app.screen.sidebar_visible
        await pilot.press("ctrl+b")
        assert app.screen.sidebar_visible


async def test_page_keys_scroll_timeline_while_editing():
    from tests.tui.test_timeline import _settle

    app = _chat_app(effects="off")
    async with app.run_test(size=(80, 24)) as pilot:
        screen = app.screen
        for n in range(30):
            screen.timeline.add_card(UserCard(str(n), number=n, timestamp="t"))
        assert await _settle(pilot, lambda: screen.timeline.stuck_to_bottom)
        await pilot.press("pageup")
        await pilot.pause()
        assert not screen.timeline.stuck_to_bottom
        assert screen.input_dock._area.has_focus


async def test_clear_removes_visible_conversation():
    conv = FakeConversation()
    conv.clear_history = lambda: conv.messages.clear()
    app = _chat_app(conv, effects="off")
    async with app.run_test() as pilot:
        app.screen.submit_prompt("hello")
        await pilot.pause(0.3)
        assert list(app.screen.query(UserCard))
        app.screen.dispatch_command("/clear")
        await pilot.pause()
        assert not list(app.screen.query(UserCard))


async def test_click_card_title_then_toggle_with_keyboard():
    app = _chat_app(effects="off")
    async with app.run_test(size=(80, 24)) as pilot:
        card = UserCard("hello", number=1, timestamp="t")
        app.screen.timeline.add_card(card)
        await pilot.pause()
        await pilot.click(card._title_widget)
        assert card.collapsed
        await pilot.press("ctrl+o")
        assert not card.collapsed


async def test_escape_dismisses_completion_before_cancelling_turn():
    app = _chat_app(effects="off")
    async with app.run_test() as pilot:
        screen = app.screen
        cancelled = []
        screen._busy = True
        screen.cancel_turn = lambda: cancelled.append(True)
        await pilot.press("/", "escape")
        assert not screen.input_dock.completion_open
        assert cancelled == []
        await pilot.press("escape")
        assert cancelled == [True]


async def test_same_tool_twice_tracks_cards_by_call_id():
    from neow.tui.bridge.events import Notice, ToolFinished, ToolStarted
    from neow.tui.widgets.cards import SystemCard, ToolCard

    app = _chat_app(effects="off")
    async with app.run_test(size=(120, 40)) as pilot:
        screen = app.screen
        screen.handle_event(ToolStarted(name="read_file", args={}, call_id="c1"))
        screen.handle_event(ToolStarted(name="read_file", args={}, call_id="c2"))
        screen.handle_event(
            ToolFinished(
                name="read_file",
                result="ok",
                is_error=False,
                denied=False,
                call_id="c1",
            )
        )
        screen.handle_event(Notice(message="Stopped after 50 requests", level="warn"))
        await pilot.pause()

        first, second = list(screen.query(ToolCard))
        assert first.status_icon == "✓"
        assert second.status_icon == "⟳"
        assert any("Stopped" in c.message for c in screen.query(SystemCard))


async def test_context_usage_shown_and_auto_compact_after_turn():
    from neow.tui.widgets.cards import CompactionCard

    calls = []
    conv = FakeConversation(
        script=[Chunk(content_delta="ok"), Chunk(finish_reason="stop")],
        context_usage=lambda: (85_000, 100_000, 85.0),
        should_auto_compact=lambda: not calls,
    )
    conv.compact_incremental = (
        lambda **kw: calls.append(kw) or "Compacted 6 old messages"
    )
    app = _chat_app(conv, effects="off")
    async with app.run_test(size=(120, 40)) as pilot:
        screen = app.screen
        screen.submit_prompt("hello")
        for _ in range(40):
            await pilot.pause(0.05)
            if list(screen.query(CompactionCard)) and not screen.busy:
                break
        cards = list(screen.query(CompactionCard))
        assert calls and cards
        assert "Compacted 6 old messages" in cards[-1].message
        assert not screen.busy
        assert screen.status_bar._context_pct == 85.0
        assert "ctx" in str(screen.status_bar.render())
