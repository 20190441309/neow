"""MCP client: tools from Model Context Protocol servers.

Servers come from the ``mcp.servers`` section of the Neow config and from
``.mcp.json`` at the project root (Claude Code's format)::

    {"mcpServers": {
        "files": {"command": "npx", "args": ["-y", "server"], "env": {}},
        "docs":  {"type": "http", "url": "https://host/mcp", "headers": {}}
    }}

Each server's tools are registered as ``mcp__<server>__<tool>``. They need
approval like shell commands unless the server is marked ``"trusted": true``
or the tool declares ``readOnlyHint``. Servers defined by the project (which
anyone who can commit to the repository controls) only start after the user
approved that exact configuration once.

The SDK is asynchronous; one background thread runs an event loop that owns
every connection, and the agent calls tools through blocking wrappers with a
timeout. A server that fails to start is reported by ``/mcp`` and never
affects the rest of Neow.
"""

import asyncio
import hashlib
import json
import os
import re
import threading
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from neow.core.approval import ApprovalTier
from neow.core.cancellation import current_cancel_token
from neow.core.tools_registry import ToolSpec
from neow.utils.logger import logger

DEFAULT_TIMEOUT = 60.0  # seconds for one tool call
CONNECT_TIMEOUT = 30.0
APPROVALS_FILE = Path.home() / ".neow" / "mcp-approved.json"
LOG_DIR = Path.home() / ".neow" / "logs"
_NAME = re.compile(r"[^A-Za-z0-9_-]")
_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


class MCPError(Exception):
    """A server is unavailable or a call failed."""


@dataclass
class ServerConfig:
    name: str
    command: str = ""
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    trusted: bool = False
    timeout: float = DEFAULT_TIMEOUT
    source: str = "user"  # "user" or "project" (needs confirmation)
    origin: str = ""  # file the entry came from

    @property
    def transport(self) -> str:
        return "http" if self.url else "stdio"

    def fingerprint(self) -> str:
        """Hash of what the server runs; approval is tied to it."""
        data = [self.command, self.args, self.env, self.url, self.headers]
        raw = json.dumps(data, sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def describe(self) -> str:
        if self.url:
            return self.url
        return " ".join([self.command, *self.args])


# ── configuration ─────────────────────────────────────────────────────────


def _expand(value: Any) -> Any:
    """``${VAR}`` / ``${VAR:-default}`` from the environment, recursively."""
    if isinstance(value, str):
        return _ENV.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    return value


def parse_servers(raw: Any, source: str, origin: str) -> Dict[str, ServerConfig]:
    """Server entries from a ``{"name": {...}}`` mapping; bad entries skipped."""
    servers: Dict[str, ServerConfig] = {}
    if not isinstance(raw, dict):
        return servers
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            logger.warning(f"MCP server {name!r} in {origin}: entry must be an object")
            continue
        entry = _expand(entry)
        kind = entry.get("type", "http" if entry.get("url") else "stdio")
        if kind in ("http", "streamable-http", "streamable_http"):
            if not entry.get("url"):
                logger.warning(f"MCP server {name!r} in {origin}: missing url")
                continue
        elif kind == "stdio":
            if not entry.get("command"):
                logger.warning(f"MCP server {name!r} in {origin}: missing command")
                continue
        else:
            logger.warning(
                f"MCP server {name!r} in {origin}: unsupported type {kind!r}"
            )
            continue
        servers[name] = ServerConfig(
            name=name,
            command=str(entry.get("command", "")) if kind == "stdio" else "",
            args=[str(a) for a in entry.get("args", [])] if kind == "stdio" else [],
            env={k: str(v) for k, v in (entry.get("env") or {}).items()},
            url=str(entry.get("url", "")) if kind != "stdio" else "",
            headers={k: str(v) for k, v in (entry.get("headers") or {}).items()},
            trusted=bool(entry.get("trusted", False)),
            timeout=float(entry.get("timeout", DEFAULT_TIMEOUT)),
            source=source,
            origin=origin,
        )
    return servers


def load_server_configs(
    config_servers: Any,
    config_source: str,
    config_origin: str,
    project_dir: Path,
) -> Dict[str, ServerConfig]:
    """Config servers, then ``.mcp.json`` from *project_dir* (wins on name clash)."""
    servers = parse_servers(config_servers, config_source, config_origin)
    mcp_json = Path(project_dir) / ".mcp.json"
    if mcp_json.is_file():
        try:
            data = json.loads(mcp_json.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning(f"Ignoring {mcp_json}: {exc}")
        else:
            servers.update(
                parse_servers(data.get("mcpServers"), "project", str(mcp_json))
            )
    return servers


# ── project approvals ─────────────────────────────────────────────────────


def _approval_key(server: ServerConfig) -> str:
    return f"{server.origin}::{server.name}"


def is_approved(server: ServerConfig, path: Path = APPROVALS_FILE) -> bool:
    if server.source != "project":
        return True
    try:
        approved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return approved.get(_approval_key(server)) == server.fingerprint()


def remember_approval(server: ServerConfig, path: Path = APPROVALS_FILE) -> None:
    try:
        approved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        approved = {}
    approved[_approval_key(server)] = server.fingerprint()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(approved, indent=2), encoding="utf-8")


# ── results ───────────────────────────────────────────────────────────────


def format_result(result: Any) -> str:
    """CallToolResult -> text for the model (errors start with ``Error:``)."""
    parts: List[str] = []
    for block in getattr(result, "content", None) or []:
        kind = getattr(block, "type", "")
        if kind == "text":
            parts.append(block.text)
        elif kind in ("image", "audio"):
            parts.append(f"[{kind}: {getattr(block, 'mime_type', '')}]")
        elif kind == "resource_link":
            parts.append(f"[resource: {getattr(block, 'uri', '')}]")
        elif kind == "resource":
            resource = getattr(block, "resource", None)
            text = getattr(resource, "text", None)
            parts.append(
                text if text else f"[resource: {getattr(resource, 'uri', '')}]"
            )
        else:
            parts.append(f"[{kind or 'content'}]")
    text = "\n".join(parts)
    structured = getattr(result, "structured_content", None)
    if not text and structured is not None:
        text = json.dumps(structured, ensure_ascii=False, indent=2)
    if getattr(result, "is_error", False):
        return f"Error: {text or 'the MCP tool reported an error'}"
    return text or "(no output)"


def tool_name(server: str, tool: str) -> str:
    """``mcp__<server>__<tool>``, limited to the characters providers accept."""
    name = f"mcp__{_NAME.sub('_', server)}__{_NAME.sub('_', tool)}"
    return name[:64]


# ── connections ───────────────────────────────────────────────────────────


@dataclass
class ServerState:
    config: ServerConfig
    status: str = "pending"  # pending | connected | failed | disabled | stopped
    error: str = ""
    tools: List[Any] = field(default_factory=list)  # mcp Tool objects
    client: Any = None
    stop: Optional[asyncio.Event] = None
    task: Optional[asyncio.Task] = None


class MCPManager:
    """Owns the event loop thread and every server connection."""

    def __init__(self, servers: Dict[str, ServerConfig]):
        self.states: Dict[str, ServerState] = {
            name: ServerState(config) for name, config in servers.items()
        }
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="neow-mcp", daemon=True
        )
        self._thread.start()
        self._registry: Any = None

    # -- lifecycle ------------------------------------------------------

    def _submit(self, coro) -> Future:
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def attach(self, registry: Any) -> None:
        """Keep *registry* in sync: servers add their tools when they connect."""
        self._registry = registry
        for state in self.states.values():
            self._sync_tools(state)

    def start(
        self,
        names: Optional[List[str]] = None,
        timeout: float = CONNECT_TIMEOUT,
        wait: bool = True,
    ) -> None:
        """Connect to the named servers (default: all pending) in parallel.

        With ``wait=False`` this returns at once; tools appear in the attached
        registry as each server comes up.
        """
        names = (
            names
            if names is not None
            else [n for n, s in self.states.items() if s.status == "pending"]
        )
        ready = [self._submit(self._connect(self.states[n])) for n in names]
        if not wait:
            return
        deadline = time.monotonic() + timeout
        for name, future in zip(names, ready):
            try:
                future.result(timeout=max(0.1, deadline - time.monotonic()))
            except FutureTimeout:
                state = self.states[name]
                state.status, state.error = "failed", f"no response in {timeout:.0f}s"
                self._submit(self._disconnect(state))
            except Exception as exc:  # already recorded on the state
                logger.debug(f"MCP {name}: {exc}")

    async def _connect(self, state: ServerState) -> None:
        state.status, state.error, state.tools = "pending", "", []
        state.stop = asyncio.Event()
        connected = asyncio.get_running_loop().create_future()
        state.task = asyncio.ensure_future(self._serve(state, connected))
        await connected

    async def _serve(self, state: ServerState, connected: "asyncio.Future") -> None:
        from mcp import Client

        log = None
        try:
            transport, log = self._transport(state.config)
            async with Client(
                transport, read_timeout_seconds=state.config.timeout
            ) as client:
                tools: List[Any] = []
                cursor = None
                while True:
                    page = await client.list_tools(cursor=cursor)
                    tools.extend(page.tools)
                    cursor = page.next_cursor
                    if not cursor:
                        break
                state.client, state.tools, state.status = client, tools, "connected"
                self._sync_tools(state)
                if not connected.done():
                    connected.set_result(None)
                await state.stop.wait()
        except BaseException as exc:  # noqa: BLE001 - isolate every failure
            if state.status != "stopped":
                state.status = "failed"
                state.error = _describe_error(exc)
                logger.warning(f"MCP server {state.config.name} failed: {state.error}")
            if not connected.done():
                connected.set_exception(MCPError(state.error or "stopped"))
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
        finally:
            state.client = None
            self._sync_tools(state)
            if log is not None:
                log.close()

    def _transport(self, config: ServerConfig):
        if config.transport == "http":
            import httpx2
            from mcp.client.streamable_http import streamable_http_client

            http = httpx2.AsyncClient(headers=config.headers or None)
            return streamable_http_client(config.url, http_client=http), None
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        # The server's stderr must not reach the terminal (it would break the TUI).
        log = open(LOG_DIR / f"mcp-{_NAME.sub('_', config.name)}.log", "a")
        params = StdioServerParameters(
            command=config.command, args=config.args, env=config.env or None
        )
        return stdio_client(params, errlog=log), log

    async def _disconnect(self, state: ServerState) -> None:
        if state.stop is not None:
            state.stop.set()
        if state.task is not None:
            try:
                await asyncio.wait_for(state.task, timeout=5)
            except BaseException:  # noqa: BLE001
                state.task.cancel()

    def reconnect(self, name: str) -> ServerState:
        state = self.states[name]
        state.status = "stopped"
        self._submit(self._disconnect(state)).result(timeout=10)
        state.status = "pending"
        self.start([name])
        return state

    def close(self) -> None:
        for state in self.states.values():
            if state.status == "connected":
                state.status = "stopped"
        try:
            futures = [self._submit(self._disconnect(s)) for s in self.states.values()]
            for future in futures:
                future.result(timeout=6)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"MCP shutdown: {exc}")
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2)

    # -- tools ----------------------------------------------------------

    def call(self, server: str, tool: str, arguments: Dict[str, Any]) -> str:
        """Blocking tool call; honours the turn's cancel token and the timeout."""
        state = self.states.get(server)
        if state is None or state.status != "connected" or state.client is None:
            reason = f": {state.error}" if state and state.error else ""
            raise MCPError(f"MCP server '{server}' is not connected{reason}")
        future = self._submit(state.client.call_tool(tool, arguments or {}))
        cancel = current_cancel_token()
        deadline = time.monotonic() + state.config.timeout
        while True:
            try:
                result = future.result(timeout=0.1)
                break
            except FutureTimeout:
                if cancel is not None and cancel.cancelled():
                    future.cancel()
                    return "Error: cancelled"
                if time.monotonic() > deadline:
                    future.cancel()
                    raise MCPError(
                        f"{server}/{tool} did not answer in {state.config.timeout:.0f}s"
                    )
        return format_result(result)

    def _spec(self, config: ServerConfig, tool: Any) -> ToolSpec:
        annotations = getattr(tool, "annotations", None)
        read_only = bool(getattr(annotations, "read_only_hint", False))
        schema = dict(getattr(tool, "input_schema", None) or {})
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})

        def call(**arguments: Any) -> str:
            return self.call(config.name, tool.name, arguments)

        description = (tool.description or tool.name).strip()
        return ToolSpec(
            name=tool_name(config.name, tool.name),
            description=f"[MCP server '{config.name}'] {description}",
            parameters=schema,
            func=call,
            tier=(
                ApprovalTier.READ
                if (config.trusted or read_only)
                else ApprovalTier.EXEC
            ),
            read_only=read_only,
            source=f"mcp:{config.name}",
        )

    def _sync_tools(self, state: ServerState) -> None:
        """Make the attached registry hold exactly this server's live tools."""
        registry = self._registry
        if registry is None:
            return
        source = f"mcp:{state.config.name}"
        for name in registry.names():
            spec = registry.get(name)
            if spec is not None and spec.source == source:
                registry.unregister(name)
        if state.status == "connected" and state.client is not None:
            for tool in state.tools:
                registry.register(self._spec(state.config, tool))

    # -- display --------------------------------------------------------

    def describe(self) -> str:
        if not self.states:
            return (
                "没有配置 MCP 服务器。在项目根目录的 .mcp.json 或配置文件的 "
                "mcp.servers 中添加。"
            )
        marks = {"connected": "●", "failed": "✗", "disabled": "○", "pending": "…"}
        lines = []
        for name, state in self.states.items():
            config = state.config
            head = f"{marks.get(state.status, '·')} {name} · {state.status}"
            head += f" · {config.transport} · {config.source}"
            lines.append(head)
            lines.append(f"    {config.describe()}")
            if state.error:
                lines.append(f"    {state.error}")
            if state.tools:
                names = ", ".join(t.name for t in state.tools)
                lines.append(f"    tools ({len(state.tools)}): {names}")
        return "\n".join(lines)


def mcp_command(manager: Optional[MCPManager], args: str, wait: bool = True):
    """``/mcp`` and ``/mcp reconnect <name>``: returns ``(text, kind)``."""
    if manager is None:
        return (
            "没有配置 MCP 服务器。在项目根目录的 .mcp.json 或配置文件的 "
            "mcp.servers 中添加。",
            "info",
        )
    parts = args.split()
    if parts and parts[0] == "reconnect":
        if len(parts) != 2 or parts[1] not in manager.states:
            names = ", ".join(manager.states) or "-"
            return f"Usage: /mcp reconnect <name>  (servers: {names})", "error"
        state = manager.states[parts[1]]
        if state.status == "disabled":
            return f"{parts[1]} 未获批准；重启 Neow 后会再次询问。", "warn"
        if not wait:
            threading.Thread(
                target=manager.reconnect, args=(parts[1],), daemon=True
            ).start()
            return f"正在重连 {parts[1]}… 稍后用 /mcp 查看状态", "info"
        manager.reconnect(parts[1])
    elif parts:
        return "Usage: /mcp  |  /mcp reconnect <name>", "error"
    return manager.describe(), "info"


def _describe_error(exc: BaseException) -> str:
    """Innermost useful message (anyio wraps failures in exception groups)."""
    while getattr(exc, "exceptions", None):  # BaseExceptionGroup (3.11+)
        exc = exc.exceptions[0]
    text = str(exc) or type(exc).__name__
    return text.splitlines()[0][:300]


def start_manager(
    servers: Dict[str, ServerConfig],
    confirm: Optional[Callable[[ServerConfig], bool]] = None,
    approvals_file: Path = APPROVALS_FILE,
    wait: bool = True,
) -> MCPManager:
    """Ask about unapproved project servers, then connect the rest.

    *confirm* is asked once per new or changed project server; without it
    (non-interactive runs) such servers stay disabled.
    """
    manager = MCPManager(servers)
    for state in manager.states.values():
        config = state.config
        if is_approved(config, approvals_file):
            continue
        if confirm is not None and confirm(config):
            remember_approval(config, approvals_file)
            continue
        state.status = "disabled"
        state.error = "project server not approved (restart Neow to be asked again)"
    manager.start(wait=wait)
    return manager


__all__ = [
    "MCPError",
    "MCPManager",
    "ServerConfig",
    "format_result",
    "is_approved",
    "load_server_configs",
    "mcp_command",
    "parse_servers",
    "remember_approval",
    "start_manager",
    "tool_name",
]
