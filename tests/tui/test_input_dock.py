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


async def test_file_options_are_cached(monkeypatch):
    dock = InputDock()
    calls = []

    def fake_scan(self):
        calls.append(1)
        return ["neow/main.py"]

    monkeypatch.setattr(InputDock, "_scan_files", fake_scan)
    assert dock._file_options("ne") == ["neow/main.py"]
    assert dock._file_options("ne") == ["neow/main.py"]
    assert len(calls) == 1


async def test_completion_arrows_tab_and_enter(tmp_path):
    dock = InputDock(history_path=tmp_path / "history")
    dock._remember("previous prompt")
    async with _host(dock) as pilot:
        await pilot.press("/")
        await pilot.pause()
        assert dock._completions.highlighted == 0
        await pilot.press("down", "down", "up", "tab")
        assert dock.text() == "/clear "
        assert not dock.completion_open
        assert dock._area.has_focus
        assert dock.posted_submissions == []
        await pilot.press("enter")
        assert dock.posted_submissions == ["/clear"]


async def test_enter_accepts_candidate_without_submitting(tmp_path):
    dock = InputDock(history_path=tmp_path / "history")
    async with _host(dock) as pilot:
        await pilot.press(*"/mo", "enter")
        assert dock.text() == "/model "
        assert dock.posted_submissions == []
        await pilot.press("enter")
        assert dock.posted_submissions == ["/model"]


async def test_mouse_selects_completion_and_returns_editor_focus(tmp_path):
    dock = InputDock(history_path=tmp_path / "history")
    async with _host(dock) as pilot:
        await pilot.press(*"/mo")
        await pilot.pause()
        await pilot.click(dock._completions, offset=(1, 0))
        assert dock.text() == "/model "
        assert dock._area.has_focus
        assert not dock.completion_open


async def test_completion_escape_and_arguments(tmp_path):
    dock = InputDock(history_path=tmp_path / "history")
    async with _host(dock) as pilot:
        await pilot.press(*"/mo", "escape")
        assert dock.text() == "/mo"
        assert not dock.completion_open
        await pilot.press("d")
        assert dock.completion_open
        dock.set_text("/model deepseek")
        await pilot.pause()
        assert not dock.completion_open


async def test_completion_preserves_file_marker_and_surrounding_text(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").touch()
    dock = InputDock(history_path=tmp_path / "history")
    async with _host(dock) as pilot:
        dock.set_text("read\n  @sr please")
        dock._area.move_cursor((1, 5))
        await pilot.pause()
        assert dock.completion_options() == ["@src/main.py"]
        await pilot.press("tab")
        assert dock.text() == "read\n  @src/main.py please"
        assert dock._area.has_focus


async def test_history_restores_draft_and_resets_after_submit(tmp_path):
    dock = InputDock(history_path=tmp_path / "history")
    dock._remember("one")
    dock._remember("two")
    async with _host(dock) as pilot:
        dock.set_text("draft")
        await pilot.press("up", "up", "down", "down")
        assert dock.text() == "draft"
        await pilot.press("enter", "up")
        assert dock.text() == "draft"
        assert dock._area.cursor_location == (0, 5)


async def test_busy_commands_are_not_queued(tmp_path):
    dock = InputDock(history_path=tmp_path / "history")
    async with _host(dock) as pilot:
        dock.set_busy(True)
        dock.set_text("next prompt")
        await pilot.press("enter")
        dock.set_text("/help ")
        await pilot.press("enter")
        assert dock.queued_texts() == ["next prompt"]
        assert dock.posted_submissions == ["/help"]
        assert "next prompt" in dock._history


def test_file_scan_prunes_dependency_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dependencies = tmp_path / "node_modules"
    dependencies.mkdir()
    for n in range(5001):
        (dependencies / str(n)).touch()
    (tmp_path / "wanted.py").touch()
    assert InputDock()._scan_files() == ["wanted.py"]
