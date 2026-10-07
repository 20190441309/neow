"""Gradient helpers for TUI effects."""

from __future__ import annotations

from functools import lru_cache
from typing import Iterable, Optional, Tuple

from rich.text import Text
from textual.color import Gradient

DEFAULT_COLORS: Tuple[str, ...] = ("#22d3ee", "#a78bfa", "#f472b6", "#facc15")


@lru_cache(maxsize=8)
def _gradient(colors: Tuple[str, ...]) -> Gradient:
    return Gradient.from_colors(*colors)


GRADIENT = _gradient(DEFAULT_COLORS)


def gradient_hex(
    position: float,
    phase: float = 0.0,
    colors: Optional[Iterable[str]] = None,
) -> str:
    """Return the gradient colour at *position* shifted by *phase*.

    Both inputs wrap around the gradient; the exact right edge (position
    ``1.0``) keeps the final stop rather than wrapping to the first.
    """

    grad = _gradient(tuple(colors)) if colors else GRADIENT
    total = position + phase
    wrapped = total % 1.0
    if wrapped == 0.0 and total >= 1.0:
        wrapped = 1.0
    return grad.get_color(wrapped).hex.lower()


def gradient_text(
    text: str,
    phase: float = 0.0,
    colors: Optional[Iterable[str]] = None,
) -> Text:
    """Colour every character of *text* along the gradient (newlines unstyled)."""

    out = Text()
    lines = text.split("\n")
    for line_index, line in enumerate(lines):
        if line_index:
            out.append("\n")
        width = max(len(line) - 1, 1)
        for i, ch in enumerate(line):
            out.append(ch, style=gradient_hex(i / width, phase, colors))
    return out
