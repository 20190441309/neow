"""Minimal stdio MCP server for the MCP client tests."""

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

server = MCPServer("echo")


@server.tool()
def echo(text: str) -> str:
    """Return the text unchanged."""
    return text


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@server.tool()
def whoami(ctx: Context) -> str:
    """Return the Authorization header of the HTTP request (empty on stdio)."""
    request = getattr(ctx.request_context, "request", None)
    return request.headers.get("authorization", "") if request is not None else ""


@server.tool()
def fail(reason: str) -> str:
    """Always fails."""
    raise ValueError(reason)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 2 and sys.argv[1] == "http":
        server.run("streamable-http", host="127.0.0.1", port=int(sys.argv[2]))
    else:
        server.run("stdio")
