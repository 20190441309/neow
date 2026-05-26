"""Plugin system for Neow CLI."""

import importlib
import sys
from pathlib import Path
from types import ModuleType
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


class PluginManager:
    """Discovers, loads, and manages plugins."""

    def __init__(self, plugins_dir: Path, api: PluginAPI):
        """Initialize plugin manager.

        Args:
            plugins_dir: Directory containing plugin packages.
            api: PluginAPI instance to pass to plugins.
        """
        self.plugins_dir = Path(plugins_dir)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.api = api
        self.loaded_plugins: Dict[str, ModuleType] = {}

    def discover_and_load(self) -> List[str]:
        """Scan plugins_dir and load all valid plugins.

        Returns:
            List of successfully loaded plugin names.
        """
        loaded = []
        if not self.plugins_dir.exists():
            return loaded

        for item in sorted(self.plugins_dir.iterdir()):
            if item.is_dir() and self._is_valid_plugin(item):
                if self._load_plugin(item):
                    loaded.append(item.name)

        if loaded:
            logger.info(f"Loaded {len(loaded)} plugins: {', '.join(loaded)}")
        return loaded

    def _is_valid_plugin(self, plugin_dir: Path) -> bool:
        """Check if directory is a valid plugin (has __init__.py)."""
        return (plugin_dir / "__init__.py").exists()

    def _load_plugin(self, plugin_dir: Path) -> bool:
        """Load a single plugin package.

        Imports the plugin, calls register(api), and records it.
        Returns True on success, False on failure.
        """
        plugin_name = plugin_dir.name
        try:
            # Add parent to sys.path temporarily for import
            parent = str(plugin_dir.parent)
            if parent not in sys.path:
                sys.path.insert(0, parent)

            module = importlib.import_module(plugin_name)

            if not hasattr(module, "register"):
                logger.warning(f"Plugin '{plugin_name}' has no register() function, skipping")
                return False

            module.register(self.api)
            self.loaded_plugins[plugin_name] = module
            return True

        except Exception as e:
            logger.error(f"Failed to load plugin '{plugin_name}': {e}")
            return False
