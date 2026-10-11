#!/usr/bin/env python3
"""Generate an animated hero GIF from the real NeowApp (Textual), not a mockup.

Drives the actual app through a scripted, *paced* conversation (real
``time.sleep`` between chunks on the worker thread) and polls
``save_screenshot`` on the UI thread while it streams in, producing a
sequence of frames. A second pass rasterizes each SVG frame to PNG with
Playwright/Chromium, then Pillow assembles the PNGs into a looping GIF.

Run from the repo root (needs the dev extras + playwright + a CJK-capable
Chromium install): ``.venv/bin/python docs/assets/screenshots/animate.py``
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from tests.tui.conftest import Chunk, FakeConversation, _chat_app  # noqa: E402

OUT = Path(__file__).parent
FRAMES = OUT / "_frames"

PROMPT = "Fix grep_code: it's defined but never registered as a tool"

REASONING = (
    "Tracing why grep_code is defined but never reaches the model's tool list..."
)
REPLY_1 = (
    "Found it: `ToolExecutor.get_tool_definitions()` returns an empty list — "
    "the real definitions live in `prompts.get_tool_definitions()`. Fixing:\n\n"
    "```python\nreturn prompts.get_tool_definitions()\n```"
)
REPLY_2 = "Two tests are still failing — picking those up next."


def _words(text: str):
    """Split into chunks that stream a few characters at a time."""
    parts = text.split(" ")
    out = []
    for i, part in enumerate(parts):
        out.append(part + (" " if i < len(parts) - 1 else ""))
    return out


def _script() -> list:
    """Build the Chunk sequence streamed word-by-word for the animation."""

    items = []
    items.append(Chunk(progress={"type": "reasoning_start"}))
    for w in _words(REASONING):
        items.append(Chunk(reasoning_delta=w))
    items.append(Chunk(progress={"type": "reasoning_end"}))
    for w in _words(REPLY_1):
        items.append(Chunk(content_delta=w))
    items.append(
        Chunk(
            progress={
                "type": "tool_start",
                "name": "edit_file",
                "args": {"path": "neow/core/executor.py"},
            }
        )
    )
    items.append(
        Chunk(progress={"type": "tool_end", "name": "edit_file", "result": "+2 -1"})
    )
    items.append(
        Chunk(
            progress={
                "type": "tool_start",
                "name": "execute_command",
                "args": {"command": "pytest -q"},
            }
        )
    )
    items.append(
        Chunk(
            progress={
                "type": "tool_end",
                "name": "execute_command",
                "result": "2 failed, 43 passed",
            }
        )
    )
    for w in _words(REPLY_2):
        items.append(Chunk(content_delta=w))
    items.append(Chunk(finish_reason="stop"))
    return items


class _ThrottledFakeConversation(FakeConversation):
    """Like FakeConversation, but sleeps a bit before each yielded chunk."""

    def __init__(self, script, delay: float, **attrs):
        super().__init__(script=script, **attrs)
        self._delay = delay

    def get_response_stream(self, user_input: str, cancel=None):
        self.stream_consumed = True
        self.cancel_token = cancel
        for item in self.script:
            time.sleep(self._delay)
            if isinstance(item, BaseException):
                raise item
            yield item


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        tui={"effects": "off", "theme": "midnight", "sidebar_default": True}
    )


async def record(step: float = 0.12, chunk_delay: float = 0.035, hold_frames: int = 6) -> list[Path]:
    FRAMES.mkdir(exist_ok=True)
    for f in FRAMES.glob("*.svg"):
        f.unlink()

    script = _script()
    conversation = _ThrottledFakeConversation(
        script,
        chunk_delay,
        model_client=SimpleNamespace(model="deepseek-v4-flash"),
    )
    app = _chat_app(conversation, config=_config())

    frames: list[Path] = []
    async with app.run_test(size=(132, 40)) as pilot:
        await pilot.pause()
        frame = FRAMES / f"f{len(frames):03d}.svg"
        app.save_screenshot(str(frame))
        frames.append(frame)

        app.screen.submit_prompt(PROMPT)

        # Poll while the worker thread streams the paced script in.
        total_chunks = len(script)
        est_duration = total_chunks * chunk_delay + 0.5
        elapsed = 0.0
        while elapsed < est_duration:
            await pilot.pause(step)
            elapsed += step
            frame = FRAMES / f"f{len(frames):03d}.svg"
            app.save_screenshot(str(frame))
            frames.append(frame)

        # Hold the final, settled frame so the GIF pauses before looping.
        for _ in range(hold_frames):
            frame = FRAMES / f"f{len(frames):03d}.svg"
            app.save_screenshot(str(frame))
            frames.append(frame)

    return frames


def rasterize(frames: list[Path]) -> list[Path]:
    from playwright.sync_api import sync_playwright

    pngs: list[Path] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1700, "height": 1100})
        page.route("**://cdnjs.cloudflare.com/**", lambda route: route.abort())
        for svg in frames:
            page.goto(f"file://{svg.resolve()}", wait_until="load", timeout=15000)
            png = svg.with_suffix(".png")
            page.screenshot(path=str(png))
            pngs.append(png)
        browser.close()
    return pngs


def assemble_gif(pngs: list[Path], out_path: Path, frame_ms: int = 120, hold_ms: int = 1800) -> None:
    from PIL import Image

    images = [Image.open(p).convert("RGB") for p in pngs]
    durations = [frame_ms] * len(images)
    durations[-1] = hold_ms
    durations[0] = hold_ms // 3
    images[0].save(
        out_path,
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=0,
        disposal=2,
        optimize=False,
    )


def main() -> None:
    frames = asyncio.run(record())
    print(f"recorded {len(frames)} frames")
    pngs = rasterize(frames)
    print(f"rasterized {len(pngs)} pngs")
    assemble_gif(pngs, OUT / "hero.gif")
    shutil.rmtree(FRAMES)
    print("ANIMATION OK ->", OUT / "hero.gif")


if __name__ == "__main__":
    main()
