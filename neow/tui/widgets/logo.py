"""Top bar wordmark with a gradient splash animation."""

from __future__ import annotations

from typing import Optional

from rich.text import Text
from textual.widgets import Static

from neow.tui.effects.gradient import gradient_text

MARK = "◆ NEOW"


class NeowLogo(Static):
    """Animated gradient mark; collapses 600ms after mount or on any key."""

    def __init__(self, *, effects: str = "full"):
        super().__init__()
        self.effects = effects
        self._phase = 0.0
        self._timer = None
        self._splash_timer = None
        self._collapsed = effects != "full"
        self._paint()

    # -- lifecycle -----------------------------------------------------

    def on_mount(self) -> None:
        self.start_splash()
        if self.effects == "full":
            self._splash_timer = self.set_timer(0.6, self.collapse_splash)
        self._paint()

    def start_splash(self) -> None:
        """(Re)start the 12fps gradient animation (full effects mode only)."""

        if self.effects != "full":
            return
        self._collapsed = False
        if self._timer is None:
            self._timer = self.set_interval(1 / 12, self._tick)

    def _tick(self) -> None:
        self._phase = (self._phase + 0.02) % 1.0
        self._paint()

    def _paint(self) -> None:
        self.update(gradient_text(MARK, self._phase))

    def collapse_splash(self) -> None:
        """Stop the animation and keep the static mark (idempotent)."""

        if self._collapsed:
            return
        self._collapsed = True
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if self._splash_timer is not None:
            try:
                self._splash_timer.stop()
            except Exception:
                pass
            self._splash_timer = None
        self._paint()

    @property
    def collapsed_splash(self) -> bool:
        return self._collapsed


__all__ = ["NeowLogo", "MARK"]
