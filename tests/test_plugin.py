"""Tests for plugin system."""

from unittest.mock import MagicMock

from neow.core.plugin import EventBus, PluginAPI


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
