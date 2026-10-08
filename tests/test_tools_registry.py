"""Tests for the unified tool registry (plan task 0.1)."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from neow.cli.main import setup_tools
from neow.core.approval import ApprovalMode, ApprovalPolicy, ApprovalTier
from neow.core.conversation import ConversationManager
from neow.core.executor import ToolExecutor
from neow.core.plugin import EventBus, PluginAPI, PluginManager
from neow.core.prompts import get_tool_definitions
from neow.core.tools_registry import ToolRegistry, ToolSpec, infer_parameters

SNAPSHOT = Path(__file__).parent / "fixtures" / "tool_definitions.json"


def _tool_names(definitions):
    return [d["function"]["name"] for d in definitions]


def test_registry_definitions_match_snapshot():
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert get_tool_definitions() == expected
    assert ToolExecutor().get_tool_definitions() == expected


def test_legacy_register_tool_infers_schema():
    executor = ToolExecutor()

    def greet(name: str, times: int = 1, loud: bool = False) -> str:
        """Say hello."""
        return f"hi {name}" * times

    executor.register_tool("greet", greet)
    spec = executor.registry.get("greet")
    assert spec.description == "Say hello."
    assert spec.tier == ApprovalTier.EXEC
    assert spec.parameters == {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "times": {"type": "integer"},
            "loud": {"type": "boolean"},
        },
        "required": ["name"],
    }
    assert "greet" in _tool_names(executor.get_tool_definitions())


def test_register_tool_rebinds_known_tool_keeps_schema():
    executor = ToolExecutor()
    before = executor.registry.get("read_file")

    executor.register_tool("read_file", lambda file_path: f"read {file_path}")

    after = executor.registry.get("read_file")
    assert after.parameters == before.parameters
    assert after.tier == ApprovalTier.READ and after.read_only
    assert executor.execute("read_file", {"file_path": "a"}) == "read a"


def test_tier_from_spec_overrides_table():
    executor = ToolExecutor()
    executor.approval_policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
    executor.register_tool(
        "peek", lambda: "ok", description="Look around", tier=ApprovalTier.READ
    )
    # Unknown to TOOL_TIERS (would default to exec); the spec says read.
    assert executor.execute("peek", {}) == "ok"
    assert executor.registry.get("hashline_edit").tier == ApprovalTier.WRITE


def test_plugin_tool_visible_to_model(tmp_path):
    plugin_dir = tmp_path / "weather"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text(
        "def register(api):\n"
        "    def forecast(city: str) -> str:\n"
        "        '''Weather forecast for a city.'''\n"
        "        return 'sunny in ' + city\n"
        "    api.register_tool('forecast', forecast, read_only=True, tier='read')\n"
    )
    executor = ToolExecutor()
    PluginManager(tmp_path, PluginAPI(executor, EventBus())).discover_and_load()

    client = MagicMock()
    response = MagicMock(content="done", has_tool_calls=False, tool_calls=[], usage={})
    client.chat.return_value = response
    conversation = ConversationManager(client, tool_executor=executor)
    conversation.tool_provider = executor.get_tool_definitions
    conversation.get_response("weather?")

    sent = client.chat.call_args.kwargs["tools"]
    forecast = [d for d in sent if d["function"]["name"] == "forecast"]
    assert forecast and forecast[0]["function"]["description"] == (
        "Weather forecast for a city."
    )
    assert executor.registry.get("forecast").source == "plugin:weather"


def test_search_code_directory_is_optional(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("needle = 1\n")
    monkeypatch.chdir(tmp_path)
    executor = ToolExecutor()
    setup_tools(executor)

    result = executor.execute("search_code", {"query": "needle"})

    assert "a.py" in result


def test_registry_subset_and_copy_are_independent():
    registry = ToolRegistry(
        [
            ToolSpec("a", "A", infer_parameters(lambda: None), lambda: "a",
                     read_only=True),
            ToolSpec("b", "B", infer_parameters(lambda: None), lambda: "b"),
        ]
    )
    read_only = registry.subset(lambda spec: spec.read_only)
    clone = registry.copy()
    clone.register(ToolSpec("c", "C", {"type": "object"}, lambda: "c"))

    assert read_only.names() == ["a"]
    assert registry.names() == ["a", "b"]
    assert clone.names() == ["a", "b", "c"]
