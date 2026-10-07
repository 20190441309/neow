#!/usr/bin/env python3
"""Neow TUI 可行性验证 demo —— 一次性实验，不是产品代码。

验证 neow TUI 设计所需的 4 个视觉机制在 Textual 8.x 上可行：
  1. 渐变 ASCII logo + 色彩流动动画
  2. crush 式「乱码闪动」thinking 文本（随机字形 + 渐变 + 逐字定型）
  3. 可折叠工具调用卡片（Collapsible）
  4. 流式 Markdown 助手卡片（Markdown.append 逐步追加）

用法:
  交互:     python demo.py
  无头验证: python demo.py --headless   # 跑断言并输出 SVG 截图
"""

from __future__ import annotations

import argparse
import asyncio
import random
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.color import Gradient
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Collapsible, Footer, Markdown, Static

SCRAMBLE_RUNES = "0123456789abcdefABCDEF~!@#$%^&*()+=_<>/\\|[]{}"
GRADIENT = Gradient.from_colors("#22d3ee", "#a78bfa", "#f472b6", "#facc15")

LOGO = r"""
 ███╗   ██╗███████╗ ██████╗ ██╗    ██╗
 ████╗  ██║██╔════╝██╔═══██╗██║    ██║
 ██╔██╗ ██║█████╗  ██║   ██║██║ █╗ ██║
 ██║╚██╗██║██╔══╝  ██║   ██║██║███╗██║
 ██║ ╚████║███████╗╚██████╔╝╚███╔███╔╝
 ╚═╝  ╚═══╝╚══════╝ ╚═════╝  ╚══╝╚══╝
"""


def gradient_line(line: str, phase: float) -> Text:
    """Per-character gradient along the line, phase shifts the hue."""
    width = max(len(line) - 1, 1)
    out = Text(no_wrap=True)
    for i, ch in enumerate(line):
        color = GRADIENT.get_color(((i / width) + phase) % 1.0).hex
        out.append(ch, style=color)
    return out


class AnimatedLogo(Static):
    """Feasibility check 1: animated gradient ASCII logo."""

    def on_mount(self) -> None:
        self._phase = 0.0
        self.set_interval(1 / 12, self._tick)

    def _tick(self) -> None:
        self._phase = (self._phase + 0.02) % 1.0
        body = Text()
        for line in LOGO.strip("\n").splitlines():
            body.append_text(gradient_line(line, self._phase))
            body.append("\n")
        self.update(body)


class ScrambleText(Static):
    """Feasibility check 2: crush-style scrambled thinking text.

    Random glyphs scramble and resolve left-to-right while a gradient
    cycles across the string (20 FPS like crush's anim package).
    """

    def __init__(self, target: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.target = target
        self.progress = 0.0
        self._phase = 0.0

    def on_mount(self) -> None:
        self.set_interval(1 / 20, self._tick)

    def _tick(self) -> None:
        step = 1.0 / max(len(self.target), 1)
        self.progress = min(1.0, self.progress + step * 0.35)
        self._phase = (self._phase + 0.07) % 1.0
        self.update(self._frame())

    def _frame(self) -> Text:
        n = len(self.target)
        settled = int(n * self.progress)
        out = Text()
        for i, ch in enumerate(self.target):
            color = GRADIENT.get_color(((i / max(n - 1, 1)) + self._phase) % 1.0).hex
            if ch == " ":
                out.append(" ")
            elif i < settled:
                out.append(ch, style=color)
            else:
                out.append(random.choice(SCRAMBLE_RUNES), style=color)
        return out


class StreamCard(Vertical):
    """Feasibility check 4: assistant card with streaming markdown."""

    CHUNKS = [
        "### Analysis\n",
        "The `grep_code()` function exists but ",
        "is never registered as a tool. I'll register it ",
        "in `ToolExecutor.get_tool_definitions()`.\n\n",
        "```python\n",
        "def get_tool_definitions(self):\n",
        "    return prompts.get_tool_definitions()\n",
        "```\n",
    ]

    def compose(self) -> ComposeResult:
        yield Static("● Assistant", classes="card-title assistant")
        yield Markdown(id="stream-md")

    async def on_mount(self) -> None:
        md = self.query_one("#stream-md", Markdown)
        for chunk in self.CHUNKS:
            await md.append(chunk)
            await asyncio.sleep(0.08)


class ToolCard(Collapsible):
    """Feasibility check 3: collapsible tool-call card."""

    def __init__(self) -> None:
        super().__init__(
            Markdown(
                "```diff\n"
                "- return []\n"
                "+ return prompts.get_tool_definitions()\n"
                "```",
            ),
            title="🔧 edit_file  neow/core/executor.py  +1 -1",
            collapsed=False,
            id="tool-card",
        )


class NeowDemo(App):
    CSS = """
    Screen { background: #0b0d12; color: #e5e7eb; }
    #logo { width: auto; height: 7; padding: 0 2; }
    #timeline { padding: 1 2; }
    .card-title { padding: 0 1; text-style: bold; }
    .assistant { color: #a78bfa; }
    .thinking { color: #71717a; padding: 0 1 1 1; }
    StreamCard {
        border: round #334155; background: #0f1117;
        margin: 1 0; padding: 0 1; height: auto;
    }
    ScrambleText { padding: 0 1; }
    Collapsible {
        border: round #334155; background: #0f1117;
        margin: 1 0; padding: 0 1;
    }
    CollapsibleTitle { color: #facc15; }
    """

    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield AnimatedLogo(id="logo")
        with VerticalScroll(id="timeline"):
            with Vertical(classes="card thinking"):
                yield Static("✻ Thinking", classes="card-title thinking")
                yield ScrambleText(
                    "Let me trace how tool definitions flow from prompts.py "
                    "into the executor and why the list is empty at runtime."
                )
            yield ToolCard()
            yield StreamCard()
        yield Footer()


async def headless() -> None:
    app = NeowDemo()
    out_dir = Path("/tmp/neow-tui-feasibility")
    out_dir.mkdir(exist_ok=True)
    async with app.run_test(size=(110, 36)) as pilot:
        await pilot.pause(1.5)
        p1 = app.save_screenshot(str(out_dir / "01-effects-phase1.svg"))
        scramble = app.query_one(ScrambleText)
        assert scramble.progress > 0, "scramble animation did not advance"
        assert scramble._frame().plain, "scramble produced empty text"

        coll = app.query_one("#tool-card", Collapsible)
        coll.collapsed = True
        await pilot.pause(0.4)
        p2 = app.save_screenshot(str(out_dir / "02-tool-card-collapsed.svg"))

        coll.collapsed = False
        await pilot.pause(0.6)
        p3 = app.save_screenshot(str(out_dir / "03-tool-card-expanded.svg"))

        md = app.query_one("#stream-md", Markdown)
        assert "get_tool_definitions" in str(md._markdown), "markdown stream incomplete"
        assert list(app.query(AnimatedLogo)), "logo missing"

    print("FEASIBILITY OK")
    print("screenshots:")
    for p in (p1, p2, p3):
        print(" ", p, Path(p).stat().st_size, "bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    if args.headless:
        asyncio.run(headless())
    else:
        NeowDemo().run()
