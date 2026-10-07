"""Scramble ("乱码闪动") effect engine.

Crush-style: settled text stays readable while the leading edge shuffles
through random runes tinted with a moving gradient.
"""

from __future__ import annotations

import random
from typing import Optional

from rich.text import Text

from neow.tui.effects.gradient import gradient_hex

SCRAMBLE_RUNES = "0123456789abcdefABCDEF~!@#$%^&*()+=_"
SETTLED_STYLE = "#71717a"


class ScrambleEngine:
    """Deterministic-when-seeded scramble frames (see design spec §5.3)."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        rng: Optional[random.Random] = None,
        frontier: int = 32,
        phase_step: float = 0.05,
    ):
        self.enabled = enabled
        self.rng = rng if rng is not None else random.Random()
        self.frontier = frontier
        self.phase_step = phase_step

    def frame(self, settled: str, frontier: str, phase: float) -> Text:
        """Build one frame: dim settled text plus a scrambled frontier."""

        out = Text()
        if not self.enabled:
            out.append(f"{settled} {frontier}")
            return out
        out.append(settled, style=SETTLED_STYLE)
        front = frontier[-self.frontier :] if self.frontier > 0 else frontier
        width = max(len(front) - 1, 1)
        for i in range(len(front)):
            color = gradient_hex(i / width, phase)
            out.append(self.rng.choice(SCRAMBLE_RUNES), style=color)
        return out

    def settle(self, text: str, phase: float = 0.0) -> Text:
        """Final, fully resolved text (dim per spec §5.3)."""

        return Text(text, style=SETTLED_STYLE)

    def advance(self, phase: float) -> float:
        """Advance the gradient phase by one frame."""

        return (phase + self.phase_step) % 1.0
