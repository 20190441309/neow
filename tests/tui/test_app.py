"""App shell tests (plan task 2)."""

from neow.tui.screens.chat import ChatScreen
from tests.tui.conftest import FakeConversation, _chat_app


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
