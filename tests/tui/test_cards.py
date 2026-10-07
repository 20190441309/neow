"""卡片组件测试（实现计划任务 4 起，后续任务扩展）。"""

from neow.tui.widgets.cards import ErrorCard, SystemCard, UserCard
from tests.tui.conftest import _host


async def test_card_toggle_collapses_body():
    card = UserCard("hello", number=1, timestamp="12:04")
    async with _host(card) as pilot:
        assert not card.collapsed
        card.toggle()
        await pilot.pause()
        assert card.collapsed and not card.body.display


async def test_user_card_preserves_multiline():
    card = UserCard("a\nb", number=1, timestamp="12:04")
    assert "a\nb" in card.body_text()


def test_system_card_levels():
    assert SystemCard("ok").accent == "#38bdf8"
    assert SystemCard("careful", level="warn").accent == "#facc15"


def test_error_card_accent_and_title():
    c = ErrorCard("Test Failure", "2 failed")
    assert c.accent == "#f87171" and "Test Failure" in c.title_text()
