#!/usr/bin/env python3
"""Neow TUI 设计稿 mockup —— 一次性静态演示，不是产品代码。

渲染提案中的完整界面（假数据）：
  1. 主界面（时间线 + 输入坞 + 状态栏）
  2. 侧边栏展开（上下文文件 / 会话树 / Git）
  3. 审批模态
  4. 启动 splash

无头渲染 + PNG：
  python design_mockup.py --shots
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import random
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.color import Gradient
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Collapsible, Markdown, Static

GRADIENT = Gradient.from_colors("#22d3ee", "#a78bfa", "#f472b6", "#facc15")
OUT = Path("/tmp/neow-design-mockup")


def gtext(s: str, phase: float = 0.0) -> Text:
    width = max(len(s) - 1, 1)
    out = Text()
    for i, ch in enumerate(s):
        out.append(ch, style=GRADIENT.get_color(((i / width) + phase) % 1.0).hex)
    return out


SCRAMBLE = "0123456789abcdefABCDEF~!@#$%^&*()+=_<>/\\|"


class ScrambleLine(Static):
    """静态截图里也展示乱码锋面（不再逐帧）。"""

    def __init__(self, settled: str, frontier_len: int = 40) -> None:
        super().__init__()
        self.settled = settled
        self.frontier_len = frontier_len

    def on_mount(self) -> None:
        body = Text()
        body.append(self.settled, style="#71717a")
        for i in range(self.frontier_len):
            color = GRADIENT.get_color(i / self.frontier_len * 0.6).hex
            body.append(random.choice(SCRAMBLE), style=color)
        self.update(body)


def card_title(icon: str, name: str, meta: str, cls: str = "") -> Static:
    t = Text()
    t.append(f"{icon} ", style="#e5e7eb")
    t.append(name, style="#e5e7eb bold")
    if meta:
        t.append(f"   {meta}", style="#64748b")
    return Static(t, classes=f"card-title {cls}")


def diff_text() -> Text:
    t = Text()
    t.append("- return []\n", style="#f87171 on #1c1017")
    t.append("+ return prompts.get_tool_definitions()\n", style="#34d399 on #0d1a14")
    return t


class ApprovalModal(ModalScreen):
    def compose(self) -> ComposeResult:
        can = Horizontal(
            Vertical(
                Static(
                    Text.assemble(
                        ("⚠  ", "#facc15"), ("审批请求", "#facc15 bold"),
                        ("   execute_command · tier: exec", "#64748b"),
                    ),
                    classes="modal-title",
                ),
                Static(
                    Text.assemble(
                        ("$ ", "#64748b"), ("npm test", "#e5e7eb bold"), ("\n\n", ""),
                        ("原因：", "#94a3b8"),
                        ("exec 级操作需要确认（危险命令检测：无）", "#71717a"),
                    )
                ),
                Static(
                    Text.assemble(
                        ("[y]", "#34d399 bold"), (" 允许一次    ", "#94a3b8"),
                        ("[a]", "#22d3ee bold"), (" 本会话总是允许    ", "#94a3b8"),
                        ("[n/Esc]", "#f87171 bold"), (" 拒绝", "#94a3b8"),
                    ),
                    classes="modal-hint",
                ),
                classes="modal-box",
            ),
            id="modal-center",
        )
        yield can


class MockChat(App):
    CSS = """
    $bg: #0b0d12;
    Screen { background: $bg; color: #e5e7eb; }
    #topbar { height: 1; background: #0f1117; color: #64748b; padding: 0 1; }
    #body { height: 1fr; }
    #timeline { width: 1fr; padding: 1 2; }
    #timeline > * { margin: 0 0 1 0; }
    #sidebar { width: 42; display: none; border-left: solid #1e293b;
               background: #0d1016; padding: 1; }
    #sidebar.visible { display: block; }
    #inputdock { height: 4; border-top: solid #1e293b; padding: 0 1; }
    #statusbar { height: 1; background: #0f1117; color: #64748b; padding: 0 1; }
    .card { background: #0f1117; border-left: heavy #334155; padding: 0 2; }
    .card.user { border-left: heavy #22d3ee; }
    .card.assistant { border-left: heavy #a78bfa; }
    .card.thinking { border-left: heavy #52525b; }
    .card.tool { border-left: heavy #facc15; padding: 0 1; }
    .card.tool.ok { border-left: heavy #34d399; }
    .card.error { border-left: heavy #f87171; }
    .card.compact { border-left: heavy #38bdf8; }
    .card-title { padding: 0; }
    .card-body { color: #cbd5e1; padding: 0; }
    .sect { color: #475569; text-style: bold; }
    Collapsible { background: #0f1117; border: none; padding: 0; margin: 0; }
    Collapsible > Contents { padding: 0 1; }
    CollapsibleTitle { background: #0f1117; color: #94a3b8; padding: 0; }
    CollapsibleTitle:hover { background: #151a23; }
    Markdown { background: #0f1117; }
    #splash-logo { width: auto; }
    #modal-center { align: center middle; height: 1fr; }
    .modal-box { width: 74; height: auto; border: round #facc15; background: #0f1117;
                 padding: 1 2; }
    .modal-title { padding: 0 0 1 0; }
    .modal-hint { padding: 1 0 0 0; }
    ApprovalModal { background: #05060a 65%; }
    """

    BINDINGS = [("s", "toggle_sidebar", "Sidebar"), ("a", "approval", "Approval")]

    def __init__(self) -> None:
        super().__init__()
        self.sidebar_on = False

    def action_toggle_sidebar(self) -> None:
        self.sidebar_on = not self.sidebar_on
        self.query_one("#sidebar").set_class(self.sidebar_on, "visible")

    def action_approval(self) -> None:
        self.push_screen(ApprovalModal())

    def compose(self) -> ComposeResult:
        yield Static(
            Text.assemble(
                ("◆ ", "#22d3ee"), ("NEOW", "#e5e7eb bold"),
                ("   ", ""), ("deepseek-v4-flash", "#a78bfa"),
                ("  ·  ", "#334155"), ("⎇ main", "#94a3b8"),
                ("  ·  ", "#334155"), ("⛨ approval: write", "#facc15"),
                ("  ·  ", "#334155"), ("~/dev/neow", "#64748b"),
            ),
            id="topbar",
        )
        with Horizontal(id="body"):
            with VerticalScroll(id="timeline"):
                # user
                with Vertical(classes="card user"):
                    yield card_title("❯", "You", "#1 · 12:04")
                    yield Static("帮我修复 grep_code 已定义但没有注册成工具的问题", classes="card-body")
                # thinking (scrambling)
                with Vertical(classes="card thinking"):
                    yield card_title("✻", "Thinking", "2.4s · reasoning", "thinking")
                    yield ScrambleLine("让我确认 tool definitions 的流向，从 prompts.py ", 36)
                # assistant with markdown + diff
                with Vertical(classes="card assistant"):
                    yield card_title("●", "Assistant", "#2 · 12:04")
                    yield Markdown(
                        "找到问题了：`ToolExecutor.get_tool_definitions()` 返回空列表，"
                        "工具定义实际在 `prompts.get_tool_definitions()`。修复：\n\n"
                        "```python\ndef get_tool_definitions(self) -> list:\n"
                        "    return prompts.get_tool_definitions()\n```"
                    )
                # tool card done + collapsed
                with Vertical(classes="card tool ok"):
                    yield Collapsible(
                        Static(diff_text(), classes="card-body"),
                        title="✓ edit_file   neow/core/executor.py   +2 -1   0.3s",
                        collapsed=True,
                    )
                # tool card running
                with Vertical(classes="card tool"):
                    yield Collapsible(
                        Static(Text("⠹ npm test 运行中…  (12s)", style="#facc15"), classes="card-body"),
                        title="⟳ execute_command   npm test",
                        collapsed=False,
                    )
                # error card
                with Vertical(classes="card error"):
                    yield card_title("✗", "Test Failure", "2 failed · 43 passed")
                    yield Static(Text("tests/test_formatter.py::test_narrow_wrap\nAssertionError: 92 != 88", style="#fca5a5"), classes="card-body")
                # compaction
                with Vertical(classes="card compact"):
                    yield card_title("◈", "Context Compacted", "18 messages → summary · -12.4k tokens")
                    yield Static(Text("旧对话已摘要保存，可在 /tree 中回看。", style="#7dd3fc"), classes="card-body")
            with Vertical(id="sidebar"):
                yield Static("CONTEXT · 3 files", classes="sect")
                yield Static(
                    Text.assemble(
                        ("  executor.py\n  repl.py\n  formatter.py", "#94a3b8"),
                        ("\n\n", ""),
                    )
                )
                yield Static("SESSION TREE", classes="sect")
                yield Static(
                    Text.assemble(
                        ("● ", "#22d3ee"), ("fix grep_code registration\n", "#cbd5e1"),
                        ("├─ ", "#475569"), ("you: 帮我修复…\n", "#64748b"),
                        ("└─ ", "#475569"), ("you: 再加个测试\n", "#64748b"),
                    )
                )
                yield Static("\nGIT", classes="sect")
                yield Static(
                    Text.assemble(
                        ("M  neow/core/executor.py\n", "#facc15"),
                        ("✓  12:04  fix: register tool definitions\n", "#34d399"),
                        ("✓  12:01  chore: snapshot\n", "#64748b"),
                    )
                )
        with Vertical(id="inputdock"):
            yield Static(
                Text.assemble(("❯ ", "#22d3ee"), ("输入消息…", "#475569"), ("▊", "#a78bfa")),
            )
            yield Static(
                Text.assemble(
                    ("  Enter 发送 · Ctrl+J 换行 · @ 文件 · / 命令 · Esc 中断", "#475569"),
                )
            )
        yield Static(
            Text.assemble(
                ("▲ 1.2k  ▼ 3.4k tokens", "#94a3b8"),
                ("   ·   ", "#334155"), ("$0.0042", "#34d399"),
                ("   ·   ", "#334155"), ("ctx 12%", "#94a3b8"),
                ("   ·   ", "#334155"), ("⏱ 3m12s", "#94a3b8"),
                ("        Ctrl+P 命令面板 · Tab 侧栏 · Ctrl+Q 退出", "#475569"),
            ),
            id="statusbar",
        )


class Splash(App):
    CSS = """
    Screen { background: #0b0d12; color: #e5e7eb; align: center middle; }
    #wrap { width: 70; height: auto; }
    #splash-logo { width: 46; height: 7; }
    """

    LOGO = r"""
 ███╗   ██╗███████╗ ██████╗ ██╗    ██╗
 ████╗  ██║██╔════╝██╔═══██╗██║    ██║
 ██╔██╗ ██║█████╗  ██║   ██║██║ █╗ ██║
 ██║╚██╗██║██╔══╝  ██║   ██║██║███╗██║
 ██║ ╚████║███████╗╚██████╔╝╚███╔███╔╝
 ╚═╝  ╚═══╝╚══════╝ ╚═════╝  ╚══╝╚══╝
"""

    def compose(self) -> ComposeResult:
        with Vertical(id="wrap"):
            yield Static(gtext(self.LOGO.strip("\n"), 0.15), id="splash-logo")
            yield Static(
                Text.assemble(
                    ("\n     a coding agent that lives in your terminal\n", "#64748b"),
                    ("     ◆ deepseek-v4-flash", "#a78bfa"),
                    ("   ·   ", "#334155"),
                    ("连接中 ", "#64748b"),
                    ("⠹⠸⠼⠴⠦⠧", "#22d3ee"),
                )
            )


async def shots() -> None:
    OUT.mkdir(exist_ok=True)
    made = []

    app = MockChat()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.4)
        made.append(app.save_screenshot(str(OUT / "01-main.svg")))
        app.action_toggle_sidebar()
        await pilot.pause(0.3)
        made.append(app.save_screenshot(str(OUT / "02-sidebar.svg")))
        app.action_toggle_sidebar()
        app.action_approval()
        await pilot.pause(0.4)
        made.append(app.save_screenshot(str(OUT / "03-approval.svg")))

    splash = Splash()
    async with splash.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        made.append(splash.save_screenshot(str(OUT / "04-splash.svg")))

    pngs = []
    for svg in made:
        png = Path(svg).with_suffix(".png")
        subprocess.run(["rsvg-convert", svg, "-o", str(png)], check=True)
        pngs.append(png)
    print("MOCKUP OK")
    for p in pngs:
        print(" ", p, p.stat().st_size, "bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shots", action="store_true")
    args = parser.parse_args()
    if args.shots:
        asyncio.run(shots())
    else:
        MockChat().run()
