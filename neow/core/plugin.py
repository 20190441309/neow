"""Plugin system for Neow CLI."""

from typing import Any, Callable, Dict, List, Optional
from pathlib import Path
from neow.utils.logger import logger


class EventBus:
    """Lightweight event bus for plugin hooks."""

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}

    def on(self, event: str, handler: Callable) -> None:
        """Register an event handler.

        Args:
            event: Event name.
            handler: Callable to invoke when event fires.
        """
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)

    def emit(self, event: str, **kwargs) -> None:
        """Fire an event, calling all registered handlers.

        Handler exceptions are logged but do not propagate.

        Args:
            event: Event name.
            **kwargs: Event data passed to handlers.
        """
        for handler in self._handlers.get(event, []):
            try:
                handler(**kwargs)
            except Exception as e:
                logger.warning(f"Event handler error ({event}): {e}")
