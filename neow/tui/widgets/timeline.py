"""Timeline scroll container with stick-to-bottom and a new-messages chip."""

from __future__ import annotations

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from neow.tui.effects.gradient import gradient_text
from neow.tui.theme import widget_palette
from neow.tui.widgets.cards.base import CardBase

WORDMARK = "█▄ █ █▀▀ █▀█ █ █ █\n█ ▀█ ██▄ █▄█ ▀▄▀▄▀"

WELCOME_TIPS = (
    ("/", "命令"),
    ("@", "引用文件"),
    ("F1", "帮助"),
    ("Ctrl+B", "侧栏"),
    ("Ctrl+P", "命令面板"),
)


class Welcome(Static):
    """Empty-timeline splash: gradient wordmark, tagline and key tips."""

    def on_mount(self) -> None:
        self.update(self.render_welcome())

    def render_welcome(self) -> Text:
        palette = widget_palette(self)
        out = gradient_text(WORDMARK, 0.0, palette["gradient"])
        out.append("\n\n")
        out.append("从一个问题开始", f"bold {palette['text']}")
        out.append("\n")
        out.append("分析代码、定位问题，或一起实现一个功能", palette["dim"])
        out.append("\n\n")
        keycap = f"bold {palette['accent1']} on {palette['elevated']}"
        for index, (key, label) in enumerate(WELCOME_TIPS):
            if index:
                out.append("   ")
            out.append(f" {key} ", keycap)
            out.append(f" {label}", palette["muted"])
        return out


class NewMessagesBanner(Static):
    """Chip shown while the user has scrolled away from the bottom."""

    DEFAULT_CSS = """
    NewMessagesBanner {
        display: none;
        dock: top;
        height: 1;
        color: $secondary;
        background: $panel;
        text-style: bold;
        padding: 0 1;
        text-align: center;
    }
    """

    def __init__(self):
        super().__init__("↓ 有新消息 · 点击回到底部", classes="new-messages-banner")

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
        self._welcome = Welcome(id="welcome")

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


__all__ = ["TimelineScroll", "NewMessagesBanner", "Welcome"]
