#!/usr/bin/env python3
"""Generate README screenshots from the real NeowApp (Textual), not a mockup.

Run from the repo root: ``.venv/bin/python docs/assets/screenshots/generate.py``
Requires the dev extras (``pip install -e ".[dev]"``) for the test fixtures.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from tests.tui.conftest import Chunk, FakeConversation, _chat_app  # noqa: E402
from neow.tui.screens.approval import ApprovalModal  # noqa: E402

OUT = Path(__file__).parent

SCRIPT = [
    Chunk(progress={"type": "reasoning_start"}),
    Chunk(
        reasoning_delta="Tracing why grep_code is defined but never reaches the model's tool list..."
    ),
    Chunk(progress={"type": "reasoning_end"}),
    Chunk(
        content_delta=(
            "Found it: `ToolExecutor.get_tool_definitions()` returns an empty list — the real "
            "definitions live in `prompts.get_tool_definitions()`. Fixing:\n\n"
            "```python\nreturn prompts.get_tool_definitions()\n```"
        )
    ),
    Chunk(
        progress={
            "type": "tool_start",
            "name": "edit_file",
            "args": {"path": "neow/core/executor.py"},
        }
    ),
    Chunk(
        progress={
            "type": "tool_end",
            "name": "edit_file",
            "result": "+2 -1",
        }
    ),
    Chunk(
        progress={
            "type": "tool_start",
            "name": "execute_command",
            "args": {"command": "pytest -q"},
        }
    ),
    Chunk(
        progress={
            "type": "tool_end",
            "name": "execute_command",
            "result": "2 failed, 43 passed",
        }
    ),
    Chunk(content_delta="Two tests are still failing — picking those up next."),
    Chunk(finish_reason="stop"),
]


def _config(theme: str, sidebar: bool) -> SimpleNamespace:
    return SimpleNamespace(
        tui={"effects": "off", "theme": theme, "sidebar_default": sidebar}
    )


def _conversation(script) -> FakeConversation:
    return FakeConversation(
        script=script,
        model_client=SimpleNamespace(model="deepseek-v4-flash"),
    )


async def hero(theme: str = "midnight") -> None:
    """Main chat timeline, sidebar open, after a full turn."""
    app = _chat_app(_conversation(SCRIPT), config=_config(theme, True))
    async with app.run_test(size=(132, 40)) as pilot:
        await pilot.pause()
        app.screen.submit_prompt(
            "Fix grep_code: it's defined but never registered as a tool"
        )
        await pilot.pause(0.6)
        app.save_screenshot(str(OUT / f"hero-{theme}.svg"))


async def approval() -> None:
    """Approval modal over the chat timeline."""
    app = _chat_app(_conversation(SCRIPT[:3]), config=_config("midnight", False))
    async with app.run_test(size=(132, 40)) as pilot:
        await pilot.pause()
        app.screen.submit_prompt(
            "Fix grep_code: it's defined but never registered as a tool"
        )
        await pilot.pause(0.3)
        app.push_screen(
            ApprovalModal(
                tool="execute_command",
                params={"command": "npm test"},
                reason="exec-tier action needs confirmation (no danger-pattern match)",
            )
        )
        await pilot.pause(0.2)
        app.save_screenshot(str(OUT / "approval.svg"))


async def main() -> None:
    await hero("midnight")
    await hero("light")
    await approval()
    print("SCREENSHOTS OK")


if __name__ == "__main__":
    asyncio.run(main())
