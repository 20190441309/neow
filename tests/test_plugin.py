"""Tests for plugin system."""

from unittest.mock import MagicMock

from neow.core.plugin import EventBus, PluginAPI, PluginManager


class TestEventBus:
    """Tests for EventBus."""

    def test_init(self):
        bus = EventBus()
        assert bus._handlers == {}

    def test_on_registers_handler(self):
        bus = EventBus()
        handler = MagicMock()
        bus.on("session_start", handler)
        assert handler in bus._handlers["session_start"]

    def test_emit_calls_handlers(self):
        bus = EventBus()
        handler = MagicMock()
        bus.on("session_start", handler)
        bus.emit("session_start", conversation=MagicMock())
        handler.assert_called_once()

    def test_emit_multiple_handlers(self):
        bus = EventBus()
        h1 = MagicMock()
        h2 = MagicMock()
        bus.on("session_start", h1)
        bus.on("session_start", h2)
        bus.emit("session_start")
        h1.assert_called_once()
        h2.assert_called_once()

    def test_emit_no_handlers(self):
        bus = EventBus()
        # Should not raise
        bus.emit("session_start")

    def test_emit_handler_exception_does_not_propagate(self):
        bus = EventBus()
        bad_handler = MagicMock(side_effect=RuntimeError("boom"))
        good_handler = MagicMock()
        bus.on("session_start", bad_handler)
        bus.on("session_start", good_handler)
        bus.emit("session_start")
        # good_handler should still be called despite bad_handler failing
        good_handler.assert_called_once()

    def test_emit_passes_kwargs(self):
        bus = EventBus()
        handler = MagicMock()
        bus.on("pre_prompt", handler)
        bus.emit("pre_prompt", prompt="hello", conversation=MagicMock())
        handler.assert_called_once()
        call_kwargs = handler.call_args[1]
        assert call_kwargs["prompt"] == "hello"


class TestPluginAPI:
    """Tests for PluginAPI."""

    def test_init(self):
        from neow.core.plugin import PluginAPI
        executor = MagicMock()
        bus = EventBus()
        api = PluginAPI(executor, bus)
        assert api._executor is executor
        assert api._events is bus
        assert api.plugin_commands == {}

    def test_register_tool(self):
        from neow.core.plugin import PluginAPI
        executor = MagicMock()
        bus = EventBus()
        api = PluginAPI(executor, bus)

        def my_tool(param: str) -> str:
            return f"result: {param}"

        api.register_tool("my_tool", my_tool, "A test tool")
        executor.register_tool.assert_called_once_with("my_tool", my_tool)

    def test_register_command(self):
        from neow.core.plugin import PluginAPI
        bus = EventBus()
        api = PluginAPI(MagicMock(), bus)

        handler = MagicMock()
        api.register_command("/my-cmd", handler, "A test command")
        assert "/my-cmd" in api.plugin_commands
        assert api.plugin_commands["/my-cmd"] is handler

    def test_register_multiple_commands(self):
        from neow.core.plugin import PluginAPI
        api = PluginAPI(MagicMock(), EventBus())
        api.register_command("/cmd1", MagicMock())
        api.register_command("/cmd2", MagicMock())
        assert len(api.plugin_commands) == 2

    def test_on_event(self):
        from neow.core.plugin import PluginAPI
        bus = EventBus()
        api = PluginAPI(MagicMock(), bus)

        handler = MagicMock()
        api.on_event("session_start", handler)
        bus.emit("session_start", conversation=MagicMock())
        handler.assert_called_once()


class TestPluginManager:
    """Tests for PluginManager."""

    def test_init(self, tmp_path):
        from neow.core.plugin import PluginManager, PluginAPI, EventBus
        api = PluginAPI(MagicMock(), EventBus())
        manager = PluginManager(tmp_path / "plugins", api)
        assert manager.plugins_dir == tmp_path / "plugins"

    def test_discover_empty_dir(self, tmp_path):
        from neow.core.plugin import PluginManager, PluginAPI, EventBus
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        api = PluginAPI(MagicMock(), EventBus())
        manager = PluginManager(plugins_dir, api)
        loaded = manager.discover_and_load()
        assert loaded == []

    def test_discover_creates_dir(self, tmp_path):
        from neow.core.plugin import PluginManager, PluginAPI, EventBus
        plugins_dir = tmp_path / "nonexistent"
        api = PluginAPI(MagicMock(), EventBus())
        manager = PluginManager(plugins_dir, api)
        assert plugins_dir.exists()

    def test_is_valid_plugin(self, tmp_path):
        from neow.core.plugin import PluginManager, PluginAPI, EventBus
        api = PluginAPI(MagicMock(), EventBus())
        manager = PluginManager(tmp_path, api)

        # Valid: has __init__.py
        plugin_dir = tmp_path / "my_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("def register(api): pass\n")
        assert manager._is_valid_plugin(plugin_dir) is True

        # Invalid: no __init__.py
        bad_dir = tmp_path / "bad_plugin"
        bad_dir.mkdir()
        assert manager._is_valid_plugin(bad_dir) is False

    def test_load_valid_plugin(self, tmp_path):
        from neow.core.plugin import PluginManager, PluginAPI, EventBus
        executor = MagicMock()
        bus = EventBus()
        api = PluginAPI(executor, bus)
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        plugin_dir = plugins_dir / "test_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text(
            "def register(api):\n"
            "    api.register_tool('test_tool', lambda: 'ok', 'test')\n"
            "    api.register_command('/test-cmd', lambda args: None)\n"
            "    api.on_event('session_start', lambda **kw: None)\n"
        )

        manager = PluginManager(plugins_dir, api)
        loaded = manager.discover_and_load()

        assert "test_plugin" in loaded
        executor.register_tool.assert_called_once()
        assert "/test-cmd" in api.plugin_commands

    def test_load_plugin_without_register(self, tmp_path):
        """Plugin without register() function is skipped."""
        from neow.core.plugin import PluginManager, PluginAPI, EventBus
        api = PluginAPI(MagicMock(), EventBus())
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        plugin_dir = plugins_dir / "bad_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("# no register function\n")

        manager = PluginManager(plugins_dir, api)
        loaded = manager.discover_and_load()
        assert loaded == []

    def test_load_plugin_exception_does_not_crash(self, tmp_path):
        """Plugin that raises during register is skipped."""
        from neow.core.plugin import PluginManager, PluginAPI, EventBus
        api = PluginAPI(MagicMock(), EventBus())
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        plugin_dir = plugins_dir / "crash_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text(
            "def register(api):\n"
            "    raise RuntimeError('plugin crash')\n"
        )

        manager = PluginManager(plugins_dir, api)
        loaded = manager.discover_and_load()
        assert loaded == []

    def test_load_multiple_plugins(self, tmp_path):
        from neow.core.plugin import PluginManager, PluginAPI, EventBus
        executor = MagicMock()
        api = PluginAPI(executor, EventBus())
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        for name in ["plugin_a", "plugin_b"]:
            d = plugins_dir / name
            d.mkdir()
            (d / "__init__.py").write_text(
                f"def register(api):\n    api.register_tool('{name}_tool', lambda: 'ok')\n"
            )

        manager = PluginManager(plugins_dir, api)
        loaded = manager.discover_and_load()
        assert len(loaded) == 2
        assert "plugin_a" in loaded
        assert "plugin_b" in loaded
