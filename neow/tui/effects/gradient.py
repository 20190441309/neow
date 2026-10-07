"""Gradient helpers for TUI effects.

The palette matches the design spec (§8.1): cyan → violet → pink → amber.
"""

from __future__ import annotations

from rich.text import Text
from textual.color import Gradient

GRADIENT = Gradient.from_colors("#22d3ee", "#a78bfa", "#f472b6", "#facc15")


def gradient_hex(position: float, phase: float = 0.0) -> str:
    """Return the gradient colour at *position* shifted by *phase*.

    Both inputs wrap around the gradient; the exact right edge (position
    ``1.0``) keeps the final stop rather than wrapping to the first.
    """

    total = position + phase
    wrapped = total % 1.0
    if wrapped == 0.0 and total >= 1.0:
        wrapped = 1.0
    return GRADIENT.get_color(wrapped).hex.lower()


def gradient_text(text: str, phase: float = 0.0) -> Text:
    """Colour every character of *text* along the gradient (newlines unstyled)."""

    out = Text()
    lines = text.split("\n")
    for line_index, line in enumerate(lines):
        if line_index:
            out.append("\n")
        width = max(len(line) - 1, 1)
        for i, ch in enumerate(line):
            out.append(ch, style=gradient_hex(i / width, phase))
    return out
