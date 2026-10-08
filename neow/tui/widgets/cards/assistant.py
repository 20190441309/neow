"""Streaming assistant card with markdown and a live cursor."""

from __future__ import annotations

from textual.widgets import Markdown, Static

from neow.tui.theme import MIDNIGHT, widget_palette
from neow.tui.widgets.cards.base import CardBase

CURSOR = "▊"
MAX_LINES = 300


class AssistantCard(CardBase):
    """One assistant content segment; streamed markdown plus ``▊`` cursor."""

    DEFAULT_CSS = """
    AssistantCard Markdown {
        padding: 0;
        margin: 0;
    }
    AssistantCard Markdown > MarkdownParagraph:last-child,
    AssistantCard Markdown > MarkdownFence:last-child {
        margin-bottom: 0;
    }
    AssistantCard MarkdownFence > Label {
        padding: 1 2 1 1;
    }
    AssistantCard MarkdownHeader {
        margin: 1 0 1 0;
    }
    AssistantCard .stream-cursor {
        height: 1;
    }
    """

    accent_key = "role_assistant"
    title_key = "role_assistant"

    def __init__(
        self,
        *,
        number: int,
        timestamp: str,
        effects: str = "full",
        label: str = "Assistant",
    ):
        super().__init__(
            title=label,
            icon="◆",
            meta=timestamp,
            accent=MIDNIGHT["role_assistant"],
        )
        self.number = number
        self._timestamp = timestamp
        self.effects = effects
        self._content = ""
        self._pending = ""
        self._shown = ""
        self._appended_lines = 0
        self._dropped_lines = 0
        self._finished = False
        self._cursor_timer = None
        self._blink_on = True
        self._md = Markdown("")
        self._truncation = Static("", classes="truncation-hint")
        self._truncation.display = False
        self._cursor = Static(CURSOR, classes="stream-cursor")
        self.add_body(self._md, "")
        self.add_body(self._truncation, "")
        self.add_body(self._cursor, "")

    async def append_content(self, text: str) -> None:
        """Append a streamed delta; buffers until the card is mounted."""

        self._content += text
        self._pending += text
        if self.is_mounted:
            await self._flush_pending()

    def on_mount(self) -> None:
        super().on_mount()
        self._cursor.styles.color = widget_palette(self)["accent2"]
        if self._pending:
            self.call_later(self._flush_pending)
        if self.effects == "full" and not self._finished:
            self._cursor_timer = self.set_interval(0.5, self._blink)

    def _blink(self) -> None:
        if not self.is_mounted or self._finished:
            return
        palette = widget_palette(self)
        self._blink_on = not self._blink_on
        self._cursor.styles.color = (
            palette["accent2"] if self._blink_on else palette["muted"]
        )

    async def _flush_pending(self) -> None:
        if not self._pending:
            return
        self._pending = ""
        total_lines = self._content.count("\n") + 1
        visible = "\n".join(self._content.split("\n")[:MAX_LINES])
        delta = visible[len(self._shown) :]
        self._shown = visible
        self._appended_lines = min(total_lines, MAX_LINES)
        self._dropped_lines = max(total_lines - MAX_LINES, 0)
        self._truncation.update(self.truncation_hint())
        self._truncation.display = bool(self._dropped_lines)
        if delta:
            await self._md.append(delta)

    def finish(self, duration: float) -> None:
        """End the stream: hide the cursor and record the duration."""

        self._finished = True
        if self._cursor_timer is not None:
            self._cursor_timer.stop()
            self._cursor_timer = None
        self._cursor.display = False
        self.set_title(meta=f"{self._timestamp} · {duration:.1f}s")

    @property
    def cursor_visible(self) -> bool:
        return bool(self._cursor.display) and not self._finished

    def rendered_markdown(self) -> str:
        return self._content

    def markdown_text(self) -> str:
        """Text actually delivered to the markdown widget."""

        return self._shown

    def meta_text(self) -> str:
        return self._meta

    def truncation_hint(self) -> str:
        if self._dropped_lines:
            return f"… (+{self._dropped_lines} 行)"
        return ""


__all__ = ["AssistantCard", "MAX_LINES"]
