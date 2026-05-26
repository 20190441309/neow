"""Tests for plugin system."""

from unittest.mock import MagicMock

from neow.core.plugin import EventBus


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
