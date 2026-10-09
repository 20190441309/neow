"""MCP client (plan task 4.5) against tests/fixtures/mcp_echo_server.py."""

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from neow.cli.main import setup_tools
from neow.core.agent_loop import AgentLoop
from neow.core.approval import ApprovalMode, ApprovalPolicy, ApprovalTier
from neow.core.conversation import ConversationManager
from neow.core.executor import ToolExecutor
from neow.core.mcp_client import (
    MCPManager,
    is_approved,
    load_server_configs,
    mcp_command,
    parse_servers,
    start_manager,
    tool_name,
)
from tests.test_agent_loop import ScriptedClient, _call

SERVER = str(Path(__file__).parent / "fixtures" / "mcp_echo_server.py")
ECHO = {"command": sys.executable, "args": [SERVER]}


@pytest.fixture
def echo_manager(tmp_path):
    executor = ToolExecutor()
    setup_tools(executor)
    manager = start_manager(
        parse_servers({"echo": ECHO}, "user", "test"),
        approvals_file=tmp_path / "approved.json",
    )
    manager.attach(executor.registry)
    yield manager, executor
    manager.close()


def test_mcp_tools_registered_with_prefix(echo_manager):
    manager, executor = echo_manager
    names = [n for n in executor.registry.names() if n.startswith("mcp__")]
    assert names == [
        "mcp__echo__echo",
        "mcp__echo__add",
        "mcp__echo__whoami",
        "mcp__echo__fail",
    ]
    spec = executor.registry.get("mcp__echo__add")
    assert spec.source == "mcp:echo"
    assert spec.parameters["required"] == ["a", "b"]
    assert spec.description.startswith("[MCP server 'echo'] Add two integers")
    assert "mcp__echo__add" in [
        d["function"]["name"] for d in executor.get_tool_definitions()
    ]
    assert tool_name("my server", "do.it") == "mcp__my_server__do_it"


def test_mcp_call_roundtrip(echo_manager):
    manager, executor = echo_manager
    executor.approval_policy = ApprovalPolicy(mode=ApprovalMode.YOLO)
    assert executor.execute("mcp__echo__echo", {"text": "héllo"}) == "héllo"
    assert executor.execute("mcp__echo__add", {"a": 2, "b": 40}) == "42"
    assert executor.execute("mcp__echo__fail", {"reason": "x"}).startswith("Error:")

    # Through the agent loop, like a model would use it.
    client = ScriptedClient(
        [{"tool_calls": [_call("m1", "mcp__echo__add", a=1, b=2)]}, {"content": "3"}]
    )
    conv = ConversationManager(client, tool_executor=executor)
    list(AgentLoop(conv).run("add"))
    result = next(m for m in conv.messages if m["role"] == "tool")
    assert result["content"] == "3"


def test_mcp_tools_require_approval_by_default(echo_manager):
    manager, executor = echo_manager
    registry = executor.registry
    assert registry.get("mcp__echo__echo").tier == ApprovalTier.EXEC
    # readOnlyHint lowers the tier and lets calls run in parallel
    add = registry.get("mcp__echo__add")
    assert add.tier == ApprovalTier.READ and add.read_only

    executor.approval_policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
    asked = []
    executor.approval_callback = lambda name, args, reason: asked.append(name) or False
    with pytest.raises(Exception, match="denied"):
        executor.execute("mcp__echo__echo", {"text": "x"})
    assert asked == ["mcp__echo__echo"]
    assert executor.execute("mcp__echo__add", {"a": 1, "b": 1}) == "2"  # no prompt

    trusted = parse_servers({"t": dict(ECHO, trusted=True)}, "user", "test")["t"]
    tool = manager.states["echo"].tools[0]
    assert manager._spec(trusted, tool).tier == ApprovalTier.READ


def test_mcp_server_failure_is_isolated(tmp_path):
    executor = ToolExecutor()
    setup_tools(executor)
    before = set(executor.registry.names())
    manager = start_manager(
        parse_servers(
            {"broken": {"command": "/nonexistent/neow-mcp"}, "echo": ECHO},
            "user",
            "test",
        ),
        approvals_file=tmp_path / "approved.json",
    )
    try:
        manager.attach(executor.registry)
        assert manager.states["broken"].status == "failed"
        assert "No such file" in manager.states["broken"].error
        assert manager.states["echo"].status == "connected"
        assert set(executor.registry.names()) - before == {
            "mcp__echo__echo",
            "mcp__echo__add",
            "mcp__echo__whoami",
            "mcp__echo__fail",
        }
        text, _ = mcp_command(manager, "")
        assert "✗ broken · failed" in text and "● echo · connected" in text

        # Reconnecting re-registers the tools; a failed server can be retried.
        manager.reconnect("echo")
        executor.approval_policy = ApprovalPolicy(mode=ApprovalMode.YOLO)
        assert executor.execute("mcp__echo__echo", {"text": "back"}) == "back"
        text, kind = mcp_command(manager, "reconnect nope")
        assert kind == "error"
    finally:
        manager.close()
    # After shutdown the tools are gone and calls fail cleanly.
    assert not [n for n in executor.registry.names() if n.startswith("mcp__")]


def test_project_mcp_requires_confirmation(tmp_path):
    project = tmp_path / "repo"
    project.mkdir()
    (project / ".mcp.json").write_text(json.dumps({"mcpServers": {"echo": ECHO}}))
    approvals = tmp_path / "approved.json"
    servers = load_server_configs(None, "user", "cfg", project)
    assert servers["echo"].source == "project"

    asked = []
    denied = start_manager(
        servers,
        confirm=lambda s: asked.append(s.name) or False,
        approvals_file=approvals,
    )
    try:
        assert asked == ["echo"] and denied.states["echo"].status == "disabled"
    finally:
        denied.close()
    assert not is_approved(servers["echo"], approvals)

    # Non-interactive runs never start unapproved project servers.
    silent = start_manager(servers, confirm=None, approvals_file=approvals)
    assert silent.states["echo"].status == "disabled"
    silent.close()

    approved = start_manager(servers, confirm=lambda s: True, approvals_file=approvals)
    try:
        assert approved.states["echo"].status == "connected"
    finally:
        approved.close()
    assert is_approved(servers["echo"], approvals)  # remembered...

    changed = load_server_configs(None, "user", "cfg", project)["echo"]
    changed.args = changed.args + ["--extra"]
    assert not is_approved(changed, approvals)  # ...for this exact command only


def test_config_parsing_and_env_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("NEOW_TEST_TOKEN", "s3cret")
    servers = parse_servers(
        {
            "web": {
                "type": "http",
                "url": "https://example.com/mcp",
                "headers": {"Authorization": "Bearer ${NEOW_TEST_TOKEN}"},
            },
            "local": {"command": "srv", "args": ["--dir", "${MISSING:-/tmp}"]},
            "bad": {"type": "sse", "url": "https://x"},
            "nocmd": {"args": []},
        },
        "user",
        "cfg",
    )
    assert set(servers) == {"web", "local"}
    assert servers["web"].transport == "http"
    assert servers["web"].headers["Authorization"] == "Bearer s3cret"
    assert servers["local"].args == ["--dir", "/tmp"]

    # A user config entry is replaced by the project's server of the same name.
    project = tmp_path
    (project / ".mcp.json").write_text(json.dumps({"mcpServers": {"local": ECHO}}))
    merged = load_server_configs({"local": {"command": "srv"}}, "user", "cfg", project)
    assert merged["local"].source == "project"
    assert mcp_command(None, "")[0].startswith("没有配置 MCP 服务器")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_mcp_streamable_http_with_headers(tmp_path):
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, SERVER, "http", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        url = f"http://127.0.0.1:{port}/mcp"
        manager = MCPManager(
            parse_servers(
                {"web": {"url": url, "headers": {"Authorization": "Bearer t0k"}}},
                "user",
                "cfg",
            )
        )
        try:
            manager.start()
            assert manager.states["web"].status == "connected"
            assert manager.call("web", "whoami", {}) == "Bearer t0k"
        finally:
            manager.close()
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_mcp_command_in_tui_dispatcher(echo_manager):
    from types import SimpleNamespace

    from neow.cli.commands import Command, parse_command
    from neow.tui.commands import CommandDispatcher

    manager, _ = echo_manager
    assert parse_command("/mcp").command == Command.MCP
    dispatcher = CommandDispatcher(conversation=SimpleNamespace(mcp=manager))
    result = dispatcher.dispatch(parse_command("/mcp"))
    assert "● echo · connected" in result.text and "tools (4)" in result.text
    usage = dispatcher.dispatch(parse_command("/mcp bogus"))
    assert usage.kind == "error"
    empty = CommandDispatcher(conversation=SimpleNamespace(mcp=None))
    assert "没有配置" in empty.dispatch(parse_command("/mcp")).text
