"""Help screen: commands and keybindings."""

from __future__ import annotations

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from neow.tui.theme import get_palette

HELP_SECTIONS = (
    (
        "会话",
        (
            ("/help", "显示帮助"),
            ("/model", "切换模型"),
            ("/save", "保存会话"),
            ("/load", "载入会话"),
            ("/history", "历史会话"),
            ("/tree", "会话树导航"),
            ("/branch", "从节点分叉"),
            ("/compact", "压缩上下文"),
            ("/cost", "token 与费用"),
            ("/export", "导出 Markdown"),
            ("/clear", "清空会话"),
            ("/exit", "退出"),
        ),
    ),
    (
        "代码",
        (
            ("/diff", "查看未提交改动"),
            ("/commit [msg]", "提交（AI 写说明）"),
            ("/undo", "回退 AI 提交"),
            ("/lint", "运行 linter"),
            ("/test", "运行测试"),
            ("/architect", "架构师模式"),
            ("/code", "编码模式"),
            ("/approval", "审批模式"),
            ("/verbose", "工具参数展开"),
        ),
    ),
    (
        "上下文",
        (
            ("/add <file>", "加入上下文"),
            ("/drop <file>", "移出上下文"),
            ("/ls", "列出上下文"),
            ("/web <url>", "抓取网页"),
            ("/image <file>", "附加图片"),
            ("/think", "查看推理内容"),
            ("/memory", "记忆文件"),
            ("/mcp", "MCP 服务器"),
            ("/rewind", "回退改动"),
            ("/init", "生成 AGENTS.md"),
        ),
    ),
)

HELP_KEYS = (
    ("Enter", "发送"),
    ("Ctrl+J", "换行"),
    ("Esc", "中断 / 收起"),
    ("↑ ↓", "历史 / 候选"),
    ("Tab", "补全"),
    ("Ctrl+O", "折叠卡片"),
    ("Ctrl+Y", "复制代码块"),
    ("Ctrl+B", "侧栏"),
    ("Ctrl+T", "切换侧栏页"),
    ("PgUp PgDn", "滚动"),
    ("Ctrl+P", "命令面板"),
    ("Ctrl+Q", "退出"),
)


def _plain_help() -> str:
    lines = ["NEOW · 斜杠命令"]
    for _, rows in HELP_SECTIONS:
        lines.extend(f"  {name:<18} {desc}" for name, desc in rows)
    lines.append("")
    lines.append("键位")
    lines.extend(f"  {key:<18} {desc}" for key, desc in HELP_KEYS)
    return "\n".join(lines) + "\n"


HELP_TEXT = _plain_help()


def _two_columns(cells, key_width: int) -> Table:
    """Lay ``(key Text, description Text)`` pairs out in two column pairs."""

    grid = Table.grid(expand=True, padding=(0, 2, 0, 0))
    for _ in range(2):
        grid.add_column(width=key_width, no_wrap=True)
        grid.add_column(ratio=1, overflow="ellipsis", no_wrap=True)
    half = (len(cells) + 1) // 2
    for index in range(half):
        left = cells[index]
        right = cells[index + half] if index + half < len(cells) else ("", "")
        grid.add_row(*left, *right)
    return grid


def render_help(palette) -> Group:
    width = max(
        [len(name) for _, rows in HELP_SECTIONS for name, _ in rows]
        + [len(key) + 2 for key, _ in HELP_KEYS]
    )
    parts = []
    for title, rows in HELP_SECTIONS:
        parts.append(Text(title, style=f"bold {palette['accent2']}"))
        parts.append(
            _two_columns(
                [
                    (
                        Text(name, style=palette["accent1"]),
                        Text(desc, style=palette["dim"]),
                    )
                    for name, desc in rows
                ],
                width,
            )
        )
        parts.append(Text(""))
    parts.append(Text("键位", style=f"bold {palette['accent2']}"))
    keycap = f"bold {palette['text']} on {palette['elevated']}"
    parts.append(
        _two_columns(
            [
                (Text(f" {key} ", style=keycap), Text(desc, style=palette["dim"]))
                for key, desc in HELP_KEYS
            ],
            width,
        )
    )
    return Group(*parts)


class HelpScreen(ModalScreen):
    """Help overlay (F1 / /help)."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [
        ("escape", "app.pop_screen", "返回"),
        ("q", "app.pop_screen", "返回"),
    ]

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ neow · 帮助"
        box.border_subtitle = "esc 关闭"
        with box:
            with VerticalScroll():
                yield Static(id="help-text")

    def on_mount(self) -> None:
        self.query_one("#help-text", Static).update(render_help(get_palette(self.app)))
        self.query_one(VerticalScroll).focus()


__all__ = ["HelpScreen", "HELP_TEXT", "render_help"]
