"""卡片组件测试（实现计划任务 4 起，后续任务扩展）。"""

import random

from neow.tui.effects.scramble import SCRAMBLE_RUNES
from neow.tui.widgets.cards import ErrorCard, SystemCard, UserCard
from neow.tui.widgets.cards.assistant import AssistantCard
from neow.tui.widgets.cards.thinking import ThinkingCard
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


def test_thinking_frame_has_settled_prefix_and_frontier():
    card = ThinkingCard(effects="full", rng=random.Random(3), frontier=8)
    card.append_reasoning("让我确认 tool definitions 的流向 ")
    frame = card._frame().plain
    assert frame.startswith("让我确认 tool definitions 的流向 ")
    assert len(frame) > len("让我确认 tool definitions 的流向 ")


def test_finish_collapses_and_titles_duration():
    card = ThinkingCard(effects="full")
    card.append_reasoning("abc")
    card.finish_reasoning(duration=4.2)
    assert card.collapsed and "Thought" in card.title_text() and "4.2s" in card.title_text()


async def test_full_mode_runs_timer_then_stops():
    card = ThinkingCard(effects="full")
    async with _host(card) as pilot:
        assert card._timer is not None
        card.finish_reasoning(duration=1.0)
        await pilot.pause()
        assert card._timer is None


async def test_off_mode_has_no_timer():
    card = ThinkingCard(effects="off")
    card.append_reasoning("abc")
    async with _host(card):
        assert card._timer is None and "abc" in card._frame().plain


def test_subtle_mode_uses_spinner_not_runes():
    card = ThinkingCard(effects="subtle")
    card.append_reasoning("text")
    assert not (set(card._frame().plain[4:]) & set(SCRAMBLE_RUNES))


def test_huge_reasoning_truncates():
    card = ThinkingCard(effects="full")
    card.append_reasoning("x" * 10_000)
    assert len(card.body_text()) <= 10_000
    assert card.truncation_hint()


async def test_streaming_appends_markdown_and_shows_cursor():
    card = AssistantCard(number=2, timestamp="12:04")
    async with _host(card) as pilot:
        await card.append_content("找到问题了：`get_tool_definitions()`")
        await card.append_content("\n```python\nreturn prompts.get_tool_definitions()\n```")
        await pilot.pause()
        assert "get_tool_definitions" in card.rendered_markdown()
        assert card.cursor_visible


async def test_finish_removes_cursor_and_sets_meta():
    card = AssistantCard(number=2, timestamp="12:04")
    async with _host(card) as pilot:
        await card.append_content("done")
        card.finish(duration=3.1)
        await pilot.pause()
        assert not card.cursor_visible and "3.1s" in card.meta_text()


async def test_assistant_truncates_after_300_lines():
    card = AssistantCard(number=1, timestamp="12:04")
    async with _host(card) as pilot:
        await card.append_content("\n".join(f"l{i}" for i in range(310)))
        await pilot.pause()
        assert card.truncation_hint().startswith("… (+")
