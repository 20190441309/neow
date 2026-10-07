"""Timeline scroll container with stick-to-bottom and a new-messages chip."""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Static

from neow.tui.widgets.cards.base import CardBase


class NewMessagesBanner(Static):
    """Chip shown while the user has scrolled away from the bottom."""

    DEFAULT_CSS = """
    NewMessagesBanner {
        display: none;
        dock: top;
        height: 1;
        color: #a78bfa;
        background: #151a23;
        padding: 0 1;
        text-align: center;
    }
    """

    def __init__(self):
        super().__init__("↓ 新消息", classes="new-messages-banner")


class TimelineScroll(VerticalScroll):
    """Card timeline: appends cards and follows the tail when stuck."""

    DEFAULT_CSS = """
    TimelineScroll {
        height: 1fr;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._banner = NewMessagesBanner()
        self._follow_pending = False

    def compose(self):
        yield self._banner

    def add_card(self, card: CardBase) -> None:
        """Append a card; keep the view pinned if the user is at the bottom."""

        was_stuck = self.stuck_to_bottom
        self.mount(card)
        if was_stuck:
            self._schedule_follow()
        else:
            self._banner.display = True

    def _schedule_follow(self) -> None:
        """Coalesce follow-ups so a burst of adds doesn't queue many scrolls."""

        if self._follow_pending:
            return
        self._follow_pending = True
        self.call_after_refresh(self._follow_bottom)

    def _follow_bottom(self) -> None:
        self._follow_pending = False
        if self.is_mounted:
            self.scroll_end(animate=False)
            self._banner.display = False

    def cards(self) -> list[CardBase]:
        return list(self.query(CardBase))

    @property
    def stuck_to_bottom(self) -> bool:
        return self.scroll_offset.y >= self.max_scroll_y - 0.01

    def jump_to_bottom(self) -> None:
        self.scroll_end(animate=False)
        self._banner.display = False


__all__ = ["TimelineScroll", "NewMessagesBanner"]
