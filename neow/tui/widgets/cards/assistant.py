"""Streaming assistant card with markdown and a live cursor."""

from __future__ import annotations

from textual.widgets import Markdown, Static

from neow.tui.widgets.cards.base import CardBase

ACCENT = "#a78bfa"
CURSOR = "▊"
MAX_LINES = 300


class AssistantCard(CardBase):
    """One assistant content segment; streamed markdown plus ``▊`` cursor."""

    def __init__(self, *, number: int, timestamp: str):
        super().__init__(
            title=f"Assistant #{number}",
            icon="●",
            meta=f"· {timestamp}",
            accent=ACCENT,
        )
        self.number = number
        self._timestamp = timestamp
        self._content = ""
        self._pending = ""
        self._shown = ""
        self._appended_lines = 0
        self._dropped_lines = 0
        self._finished = False
        self._md = Markdown("")
        self._cursor = Static(CURSOR, classes="stream-cursor")
        self.add_body(self._md, "")
        self.add_body(self._cursor, "")

    async def append_content(self, text: str) -> None:
        """Append a streamed delta; buffers until the card is mounted."""

        self._content += text
        self._pending += text
        if self.is_mounted:
            await self._flush_pending()

    def on_mount(self) -> None:
        super().on_mount()
        if self._pending:
            self.call_later(self._flush_pending)

    async def _flush_pending(self) -> None:
        if not self._pending:
            return
        text, self._pending = self._pending, ""
        total_lines = self._content.count("\n") + 1
        if self._appended_lines >= MAX_LINES:
            self._dropped_lines = max(total_lines - MAX_LINES, 0)
            return
        if total_lines <= MAX_LINES:
            self._appended_lines = total_lines
            self._shown += text
            await self._md.append(text)
            return
        lines = text.split("\n")
        room = MAX_LINES - self._appended_lines
        kept = "\n".join(lines[:room])
        self._appended_lines += min(len(lines), room)
        self._dropped_lines = max(total_lines - self._appended_lines, 0)
        if kept:
            self._shown += kept
            await self._md.append(kept)

    def finish(self, duration: float) -> None:
        """End the stream: hide the cursor and record the duration."""

        self._finished = True
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
