"""MCP server manager screen for /mcp."""

from __future__ import annotations

from typing import Dict, List, Optional

from rich.text import Text
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from neow.tui.theme import get_palette


class McpManagerScreen(ModalScreen):
    """View connected MCP servers and mounted tools."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [
        ("escape", "app.pop_screen", "返回"),
        ("q", "app.pop_screen", "返回"),
    ]
    DEFAULT_CSS = """
    McpManagerScreen .dialog {
        width: 78;
        height: auto;
        max-height: 82%;
    }
    McpManagerScreen #mcp-header {
        margin-bottom: 1;
    }
    McpManagerScreen #mcp-scroll {
        height: auto;
        max-height: 18;
    }
    McpManagerScreen #mcp-config-hint {
        margin-top: 1;
    }
    """

    def __init__(
        self,
        *,
        servers: Optional[Dict[str, Dict]] = None,
        tools: Optional[List[str]] = None,
    ):
        super().__init__()
        self.servers = dict(servers or {})
        self.tools = list(tools or [])

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ MCP 服务"
        box.border_subtitle = "q / esc 关闭"
        palette = get_palette(self.app)
        with box:
            if not self.servers:
                header = Text()
                header.append("○ ", style=palette["muted"])
                header.append("未配置任何 MCP 服务器", style=palette["dim"])
                header.append(
                    "  ·  在 ~/.neow/config.json 中添加 mcp.servers 即可挂载",
                    style=palette["muted"],
                )
                yield Static(header, id="mcp-header")
                snippet = Text()
                snippet.append("// ~/.neow/config.json 示例\n", style=palette["muted"])
                snippet.append('"mcp"', style=palette["accent1"])
                snippet.append(": {\n  ", style=palette["dim"])
                snippet.append('"servers"', style=palette["accent2"])
                snippet.append(": {\n    ", style=palette["dim"])
                snippet.append('"filesystem"', style=palette["text"])
                fs_cfg = (
                    ': { "command": "npx", '
                    '"args": ["-y", "@modelcontextprotocol/server-filesystem", "."] }\n'
                )
                snippet.append(fs_cfg, style=palette["muted"])
                snippet.append("  }\n}", style=palette["dim"])
                yield Static(snippet, id="mcp-config-hint", classes="dialog-block")
                return

            summary = Text()
            summary.append("● ", style=palette["success"])
            summary.append(
                f"{len(self.servers)} 个服务已配置", style=f"bold {palette['text']}"
            )
            summary.append(
                f"  ·  {len(self.tools)} 个工具已挂载", style=palette["muted"]
            )
            yield Static(summary, id="mcp-header")

            with VerticalScroll(id="mcp-scroll", classes="dialog-block"):
                for name, s_info in self.servers.items():
                    cmd = s_info.get("command", "")
                    args = " ".join(str(a) for a in s_info.get("args", []))
                    full_cmd = f"{cmd} {args}".strip()
                    connected = s_info.get("connected", True)
                    dot = "● " if connected else "○ "
                    dot_color = palette["success"] if connected else palette["muted"]
                    state_label = "在线" if connected else "离线"
                    line = Text(no_wrap=True, overflow="ellipsis")
                    line.append(dot, style=dot_color)
                    line.append(f"{name:<18}", style=f"bold {palette['text']}")
                    line.append(f"{state_label:<6}", style=dot_color)
                    if full_cmd:
                        line.append(f"  {full_cmd}", style=palette["muted"])
                    yield Static(line)

                if self.tools:
                    tool_header = Text(
                        f"\n◇ 已挂载工具 ({len(self.tools)})",
                        style=f"bold {palette['accent2']}",
                    )
                    yield Static(tool_header)
                    for t in self.tools:
                        t_line = Text("  ▸ ", style=palette["accent1"])
                        t_line.append(t, style=palette["text"])
                        yield Static(t_line)

    def on_mount(self) -> None:
        if self.servers:
            self.query_one("#mcp-scroll", VerticalScroll).focus()


__all__ = ["McpManagerScreen"]
