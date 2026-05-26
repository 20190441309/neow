"""Plugin system for Neow CLI."""

from typing import Any, Callable, Dict, List
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


class PluginAPI:
    """Registration interface exposed to plugins."""

    def __init__(self, executor: Any, event_bus: EventBus):
        """Initialize plugin API.

        Args:
            executor: ToolExecutor instance for registering tools.
            event_bus: EventBus instance for registering event handlers.
        """
        self._executor = executor
        self._events = event_bus
        self.plugin_commands: Dict[str, Callable] = {}

    def register_tool(self, name: str, func: Callable, description: str = "") -> None:
        """Register an AI-callable tool.

        Args:
            name: Tool name.
            func: Tool function (func(**kwargs) -> str).
            description: Human-readable description.
        """
        self._executor.register_tool(name, func)
        logger.info(f"Plugin registered tool: {name}")

    def register_command(self, name: str, handler: Callable, description: str = "") -> None:
        """Register a /slash command.

        Args:
            name: Command name (e.g., "/my-cmd"). Must start with "/".
            handler: Command handler (handler(args: str) -> None).
            description: Human-readable description.
        """
        self.plugin_commands[name] = handler
        logger.info(f"Plugin registered command: {name}")

    def on_event(self, event: str, handler: Callable) -> None:
        """Register an event handler.

        Args:
            event: Event name (session_start, session_end, pre_prompt, post_response, file_changed).
            handler: Event handler callable.
        """
        self._events.on(event, handler)
