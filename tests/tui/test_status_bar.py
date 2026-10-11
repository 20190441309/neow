"""Tests for the status bar's elapsed-time formatting."""

import time

from neow.tui.widgets.status_bar import StatusBar
from neow.tui.theme import widget_palette


def _elapsed_text(seconds_ago: float) -> str:
    bar = StatusBar()
    bar._activity = "running execute_command"
    bar._busy_since = time.monotonic() - seconds_ago
    rendered = bar._render_left(widget_palette(bar))
    return rendered.plain


def test_elapsed_under_a_minute_shows_seconds():
    assert _elapsed_text(45).endswith("45s")


def test_elapsed_over_a_minute_rolls_over_to_minutes():
    text = _elapsed_text(167)
    assert text.endswith("2m47s")
    assert "167s" not in text


def test_elapsed_exactly_a_minute():
    assert _elapsed_text(60).endswith("1m00s")
