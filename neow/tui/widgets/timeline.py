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
        color: $secondary;
        background: $panel;
        padding: 0 1;
        text-align: center;
    }
    """

    def __init__(self):
        super().__init__("↓ 新消息", classes="new-messages-banner")

    def on_click(self) -> None:
        self.parent.jump_to_bottom()


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
        self._follow_dirty = False
        self._follow_wanted = False
        self._auto_follow = True
        self._welcome = Static(
            "[bold]从一个问题开始[/bold]\n\n"
            "分析代码、定位问题，或一起实现一个功能。\n"
            "输入 / 查看命令，@ 补全文件路径。\n\n"
            "[dim]F1 帮助    Ctrl+B 侧栏    Ctrl+P 命令面板[/dim]",
            id="welcome",
        )

    def compose(self):
        yield self._banner
        yield self._welcome

    def on_mount(self) -> None:
        self.watch(self, "virtual_size", self._content_resized)
        self.watch(self, "size", self._content_resized)

    def _content_resized(self) -> None:
        if self._auto_follow:
            self._follow_wanted = True
            self._schedule_follow()
        elif self.cards():
            self._banner.display = True

    def release_anchor(self) -> None:
        self._auto_follow = False
        self._follow_wanted = False
        self._follow_dirty = False
        super().release_anchor()

    def clear_cards(self) -> None:
        self.query(CardBase).remove()
        self._welcome.display = True
        self.jump_to_bottom()

    def add_card(self, card: CardBase) -> None:
        """Append a card; keep the view pinned if the user is at the bottom."""

        was_stuck = self.stuck_to_bottom
        self._welcome.display = False
        self.mount(card)
        if was_stuck:
            self._follow_wanted = True
            self._schedule_follow()
        else:
            self._banner.display = True

    def _schedule_follow(self) -> None:
        """Coalesce follow-ups so a burst of adds doesn't queue many scrolls.

        A follow already in flight is re-scheduled once more because layout
        may settle after it ran, leaving the viewport short of the bottom.
        """

        self._follow_dirty = True
        if self._follow_pending:
            return
        self._follow_pending = True
        self.call_after_refresh(self._follow_bottom)

    def _follow_bottom(self) -> None:
        self._follow_pending = False
        if not self._follow_wanted or not self.is_mounted:
            return
        self.scroll_end(animate=False)
        self._banner.display = False
        if self._follow_dirty:
            self._follow_dirty = False
            self._follow_pending = True
            self.call_after_refresh(self._follow_bottom)
        else:
            self._follow_wanted = False

    def scroll_up(self, *args, **kwargs) -> None:
        """User scroll cancels any pending follow (spec §4.2 stickiness)."""

        self._follow_wanted = False
        self._follow_dirty = False
        super().scroll_up(*args, **kwargs)

    def scroll_down(self, *args, **kwargs) -> None:
        self._follow_wanted = False
        self._follow_dirty = False
        super().scroll_down(*args, **kwargs)

    def cards(self) -> list[CardBase]:
        return list(self.query(CardBase))

    @property
    def stuck_to_bottom(self) -> bool:
        return self.scroll_offset.y >= self.max_scroll_y - 0.01

    def jump_to_bottom(self) -> None:
        self._auto_follow = True
        self.scroll_end(animate=False)
        self._banner.display = False

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        if self.stuck_to_bottom:
            self._auto_follow = True
            self._banner.display = False


__all__ = ["TimelineScroll", "NewMessagesBanner"]
