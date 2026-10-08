"""Timeline scroll tests (plan task 8)."""

import time

from neow.tui.widgets.cards import AssistantCard, CardBase, UserCard
from neow.tui.widgets.timeline import NewMessagesBanner, TimelineScroll
from tests.tui.conftest import _host


async def _settle(pilot, predicate, timeout: float = 3.0) -> bool:
    """Poll until *predicate* holds (follow callbacks settle across frames)."""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await pilot.pause(0.05)
    return predicate()


async def test_cards_keep_insertion_order():
    timeline = TimelineScroll()
    made = [UserCard(f"m{n}", number=n, timestamp="t") for n in range(3)]
    async with _host(timeline) as pilot:
        for card in made:
            timeline.add_card(card)
        await pilot.pause()
        assert [card.card_id for card in timeline.query(CardBase)] == [
            card.card_id for card in made
        ]
        assert timeline.scroll_y >= 0
        assert not timeline._banner.display


async def test_stick_to_bottom_and_banner():
    timeline = TimelineScroll()
    async with _host(timeline) as pilot:
        for n in range(30):
            timeline.add_card(UserCard(f"m{n}", number=n, timestamp="t"))
        assert await _settle(pilot, lambda: timeline.stuck_to_bottom)
        timeline.scroll_up(animate=False)
        await pilot.pause(0.1)
        assert not timeline.stuck_to_bottom
        timeline.add_card(UserCard("new", number=99, timestamp="t"))
        assert await _settle(
            pilot, lambda: timeline.query_one(NewMessagesBanner).display
        )
        timeline.jump_to_bottom()
        assert await _settle(pilot, lambda: timeline.stuck_to_bottom)
        assert not timeline.query_one(NewMessagesBanner).display


async def test_stream_growth_follows_until_user_scrolls():
    timeline = TimelineScroll()
    async with _host(timeline) as pilot:
        card = AssistantCard(number=1, timestamp="t", effects="off")
        timeline.add_card(card)
        await pilot.pause()
        for n in range(40):
            await card.append_content(f"paragraph {n}\n\n")
        assert await _settle(
            pilot, lambda: timeline.max_scroll_y > 0 and timeline.stuck_to_bottom
        )
        timeline.scroll_page_up(animate=False)
        await pilot.pause()
        y = timeline.scroll_y
        await card.append_content("more content\n\n" * 10)
        await pilot.pause()
        assert timeline.scroll_y == y
        assert not timeline.stuck_to_bottom
