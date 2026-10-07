"""Input dock tests (plan task 12)."""

from neow.tui.widgets.input_dock import InputDock
from tests.tui.conftest import _host


async def test_slash_completion_filters_commands():
    dock = InputDock()
    async with _host(dock) as pilot:
        await pilot.press(*"/mo")
        await pilot.pause()
        opts = dock.completion_options()
        assert any("model" in option for option in opts)
        assert not any("help" in option for option in opts)


async def test_enter_submits_and_ctrl_j_newlines():
    dock = InputDock()
    async with _host(dock) as pilot:
        await pilot.press("a", "ctrl+j", "b")
        assert "\n" in dock.text()
        await pilot.press("enter")
        assert dock.posted_submissions == ["a\nb"]


async def test_history_roundtrip(tmp_path):
    dock = InputDock(history_path=tmp_path / ".neow_history")
    dock._remember("hello")
    dock._remember("world")
    assert dock._history == ["hello", "world"]


async def test_queue_fifo_and_pop():
    dock = InputDock()
    async with _host(dock) as pilot:
        dock.set_busy(True)
        dock.enqueue("one")
        dock.enqueue("two")
        assert dock.queued_count() == 2
        await pilot.press("up")
        assert dock.text() == "two" and dock.queued_count() == 1


async def test_at_file_completion(tmp_path, monkeypatch):
    (tmp_path / "neow").mkdir()
    (tmp_path / "neow" / "main.py").write_text("")
    monkeypatch.chdir(tmp_path)
    dock = InputDock()
    async with _host(dock) as pilot:
        await pilot.press(*"@ne")
        await pilot.pause()
        assert any("neow/" in option for option in dock.completion_options())
