"""App shell and chat integration tests (plan tasks 2 and 11)."""

from types import SimpleNamespace

from neow.tui.app import resolve_effects
from neow.tui.screens.approval import ApprovalModal
from neow.tui.screens.chat import ChatScreen
from neow.tui.widgets.cards import CardBase, UserCard
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
