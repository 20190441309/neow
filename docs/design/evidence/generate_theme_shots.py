#!/usr/bin/env python3
"""Generate midnight/light theme screenshots for the polish-pack evidence.

Run from the repo root: ``.venv/bin/python docs/design/evidence/generate_theme_shots.py``
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from tests.tui.conftest import Chunk, FakeConversation, _chat_app  # noqa: E402

OUT = Path(__file__).parent

SCRIPT = [
    Chunk(progress={"type": "reasoning_start"}),
    Chunk(reasoning_delta="先确认 tool definitions 的流向，再验证注册入口。"),
    Chunk(progress={"type": "reasoning_end"}),
    Chunk(
        content_delta=(
            "找到问题了：`ToolExecutor.get_tool_definitions()` 返回空列表。\n\n"
            "```python\nreturn prompts.get_tool_definitions()\n```"
        )
    ),
    Chunk(
        progress={
            "type": "tool_start",
            "name": "execute_command",
            "args": {"command": "npm test"},
        }
    ),
    Chunk(
        progress={
            "type": "tool_end",
            "name": "execute_command",
            "result": "2 failed · 43 passed",
        }
    ),
    Chunk(content_delta="测试仍有两个失败，我会继续修复。"),
    Chunk(finish_reason="stop"),
]


async def shot(theme: str) -> None:
    config = SimpleNamespace(
        tui={"effects": "off", "theme": theme, "sidebar_default": False}
    )
    app = _chat_app(FakeConversation(script=SCRIPT), config=config)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.screen.submit_prompt("帮我修复 grep_code 没有注册的问题")
        await pilot.pause(0.6)
        svg = app.save_screenshot(str(OUT / f"tui-{theme}.svg"))
        subprocess.run(
            ["rsvg-convert", svg, "-o", str(OUT / f"tui-{theme}.png")], check=True
        )


async def main() -> None:
    for theme in ("midnight", "light"):
        await shot(theme)
    print("THEME SHOTS OK")


if __name__ == "__main__":
    asyncio.run(main())
