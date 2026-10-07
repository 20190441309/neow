"""Timeline scroll tests (plan task 8)."""

from neow.tui.widgets.cards import CardBase, UserCard
from neow.tui.widgets.timeline import NewMessagesBanner, TimelineScroll
from tests.tui.conftest import _host


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


async def test_stick_to_bottom_and_banner():
    timeline = TimelineScroll()
    async with _host(timeline) as pilot:
        for n in range(30):
            timeline.add_card(UserCard(f"m{n}", number=n, timestamp="t"))
        await pilot.pause()
        assert timeline.stuck_to_bottom
        timeline.scroll_up(animate=False)
        await pilot.pause()
        assert not timeline.stuck_to_bottom
        timeline.add_card(UserCard("new", number=99, timestamp="t"))
        await pilot.pause()
        assert timeline.query_one(NewMessagesBanner).display
        timeline.jump_to_bottom()
        await pilot.pause()
        assert timeline.stuck_to_bottom
        assert not timeline.query_one(NewMessagesBanner).display
