"""Thinking card: live reasoning with a crush-style scramble strip."""

from __future__ import annotations

import random
import time
from typing import Optional

from rich.text import Text
from textual.widgets import Static

from neow.tui.effects.scramble import ScrambleEngine
from neow.tui.theme import MIDNIGHT, widget_palette
from neow.tui.widgets.cards.base import CardBase

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
SETTLED_STYLE = MIDNIGHT["settled"]
TRUNCATE_AT = 4000


class ThinkingCard(CardBase):
    """Reasoning stream plus a scramble frontier (design spec §5.3).

    ``effects`` selects the mode: ``full`` (20 fps scramble strip),
    ``subtle`` (10 fps spinner strip) or ``off`` (static dim text).
    """

    accent_key = "role_thinking"

    def __init__(
        self,
        *,
        effects: str = "full",
        frontier: int = 32,
        fps: int = 20,
        rng: Optional[random.Random] = None,
    ):
        palette = widget_palette(None)
        super().__init__(
            title="Thinking", icon="✻", meta="", accent=palette["role_thinking"]
        )
        self.effects = effects
        self._fps = fps
        self._engine = ScrambleEngine(
            enabled=effects == "full",
            rng=rng,
            frontier=frontier,
            colors=tuple(palette["gradient"]),
            settled_color=palette["settled"],
        )
        self._reasoning = ""
        self._finished = False
        self._phase = 0.0
        self._spinner_index = 0
        self._timer = None
        self._started_at: Optional[float] = None
        self._live = Static("", classes="thinking-live")
        self.add_body(self._live, "")

    def apply_palette(self, palette) -> None:
        super().apply_palette(palette)
        if palette.get("gradient"):
            self._engine.colors = tuple(palette["gradient"])
        if palette.get("settled"):
            self._engine.settled_color = palette["settled"]
        self._apply_live()

    # -- lifecycle -----------------------------------------------------

    def on_mount(self) -> None:
        super().on_mount()
        self._started_at = time.monotonic()
        self._apply_live()
        if self.effects in ("full", "subtle"):
            interval = 1 / self._fps if self.effects == "full" else 0.1
            self._timer = self.set_interval(interval, self._tick)

    def append_reasoning(self, delta: str) -> None:
        self._reasoning += delta
        if self._timer is None:
            self._apply_live()

    def finish_reasoning(self, duration: float) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._finished = True
        self._apply_live()
        if self._reasoning:
            self.set_title(
                title="Thought",
                icon="✻",
                meta=f"{duration:.1f}s · {len(self._reasoning)} 字",
            )
        else:
            self.set_title(title="Working", icon="✻", meta=f"{duration:.1f}s")
        if not self.collapsed:
            self.toggle()

    # -- rendering -----------------------------------------------------

    def _apply_live(self) -> None:
        """Render into the live widget when mounted (update needs an app)."""

        if not self.is_mounted:
            return
        if self._finished:
            self._live.update(self._engine.settle(self._reasoning))
        else:
            self._live.update(self._frame())

    def _frame(self) -> Text:
        palette = widget_palette(self)
        if self.effects == "full":
            return self._engine.frame(
                self._reasoning + " ",
                " " * max(self._engine.frontier, 1),
                self._phase,
            )
        if self.effects == "subtle":
            spinner = SPINNER_FRAMES[self._spinner_index % len(SPINNER_FRAMES)]
            return Text.assemble(
                (self._reasoning + " ", palette["settled"]),
                (spinner, palette["accent2"]),
            )
        return Text(self._reasoning, style=palette["settled"])

    def _tick(self) -> None:
        self._phase = self._engine.advance(self._phase)
        self._spinner_index += 1
        self._apply_live()
        if self._started_at is not None and not self.collapsed:
            elapsed = time.monotonic() - self._started_at
            self.set_title(meta=f"{elapsed:.1f}s · {len(self._reasoning)} 字")

    # -- text ----------------------------------------------------------

    def body_text(self) -> str:
        return self._reasoning

    def truncation_hint(self) -> str:
        if len(self._reasoning) > TRUNCATE_AT:
            return f"… (+{len(self._reasoning) - TRUNCATE_AT} 字)"
        return ""


__all__ = ["ThinkingCard", "SPINNER_FRAMES"]
