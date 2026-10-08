"""主题与调色板测试（TUI polish 任务 1）。"""

from types import SimpleNamespace

import pytest
from textual.color import Color

from neow.core.config import Config
from neow.tui.theme import PALETTES, get_palette
from tests.tui.conftest import FakeConversation, _chat_app


def test_palettes_share_keys_and_differ():
    assert set(PALETTES["midnight"]) == set(PALETTES["light"])
    assert PALETTES["midnight"]["bg"] != PALETTES["light"]["bg"]


def test_midnight_values_are_frozen():
    assert PALETTES["midnight"]["bg"] == "#0b0d12"
    assert PALETTES["midnight"]["role_user"] == "#22d3ee"
    assert PALETTES["midnight"]["role_assistant"] == "#a78bfa"
    assert PALETTES["midnight"]["gradient"] == [
        "#22d3ee",
        "#a78bfa",
        "#f472b6",
        "#facc15",
    ]


def test_get_palette_falls_back_to_midnight():
    assert get_palette(None)["bg"] == "#0b0d12"


@pytest.mark.parametrize("theme", ["midnight", "light"])
async def test_input_border_stays_visible_without_focus(theme):
    config = SimpleNamespace(tui={"effects": "off", "theme": theme})
    app = _chat_app(config=config)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        area = app.screen.input_dock._area
        expected = ("round", Color.parse(PALETTES[theme]["accent1"]))

        def assert_border():
            for edge in ("top", "right", "bottom", "left"):
                assert getattr(area.styles.border, edge) == expected

        assert area.has_focus
        assert_border()
        original_region = area.region

        app.screen.timeline.focus()
        await pilot.pause()
        assert not area.has_focus
        assert_border()
        assert area.region == original_region

        await pilot.click(area)
        await pilot.pause()
        assert area.has_focus
        assert_border()
        assert area.region == original_region


def test_config_accepts_light_theme(tmp_path):
    p = tmp_path / ".neow.json"
    p.write_text('{"tui": {"theme": "light"}}')
    assert Config(p).tui["theme"] == "light"


async def test_app_uses_light_theme_and_palette():
    config = SimpleNamespace(
        tui={"effects": "off", "theme": "light", "sidebar_default": False}
    )
    app = _chat_app(FakeConversation(script=[]), config=config)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.theme == "neow-light"
        assert app.palette["bg"] == PALETTES["light"]["bg"]
        screen = app.screen
        screen.submit_prompt("hi")
        await pilot.pause(0.2)
        from neow.tui.widgets.cards import UserCard

        card = list(screen.query(UserCard))[-1]
        assert card.accent == PALETTES["light"]["role_user"]


def test_tool_card_applies_status_palette():
    from neow.tui.theme import LIGHT
    from neow.tui.widgets.cards import ToolCard

    card = ToolCard(effects="off")
    card.start("edit_file", {"file_path": "a.py"})
    card.apply_palette(LIGHT)
    assert card.accent == LIGHT["tool_running"]
    card.finish(result="Error: boom", is_error=True)
    card.apply_palette(LIGHT)
    assert card.accent == LIGHT["tool_error"]


def test_thinking_card_engine_follows_palette():
    from neow.tui.theme import LIGHT
    from neow.tui.widgets.cards import ThinkingCard

    card = ThinkingCard(effects="full")
    card.apply_palette(LIGHT)
    assert card._engine.colors == tuple(LIGHT["gradient"])
    assert card._engine.settled_color == LIGHT["settled"]


async def test_light_palette_reaches_status_bar():
    from neow.tui.theme import LIGHT
    from neow.tui.widgets.status_bar import StatusBar

    config = SimpleNamespace(
        tui={"effects": "off", "theme": "light", "sidebar_default": False}
    )
    app = _chat_app(FakeConversation(script=[]), config=config)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        status = app.screen.query_one(StatusBar)
        status.set_tokens(1, 2, 0.5)
        rendered = status._render_text()
        styles = " ".join(str(span.style) for span in rendered._spans)
        assert LIGHT["success"] in styles


def test_status_helpers_shorten_numbers_and_paths(monkeypatch):
    from pathlib import Path

    from neow.tui.widgets.status_bar import human_tokens, short_path

    assert human_tokens(932) == "932"
    assert human_tokens(12840) == "12.8k"
    assert human_tokens(2_500_000) == "2.50M"
    monkeypatch.setenv("HOME", "/home/me")
    assert short_path(Path("/home/me/proj")) == "~/proj"
    assert short_path(Path("/a/very/long/path/that/keeps/going/to/repo"), 12) == (
        "…/to/repo"
    )
