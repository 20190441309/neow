"""Read-before-edit guard and prompt cleanup (plan task 2.4)."""

import pytest

from neow.cli.main import setup_tools
from neow.core.executor import ToolError, ToolExecutor
from neow.core.prompts import get_system_prompt


@pytest.fixture
def executor():
    executor = ToolExecutor()
    setup_tools(executor)
    return executor


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("x = 1\n")
    return path


def _edit(executor, path, old="x = 1", new="x = 2"):
    return executor.execute(
        "edit_file", {"file_path": str(path), "old_text": old, "new_text": new}
    )


def test_edit_requires_prior_read(executor, source):
    with pytest.raises(ToolError, match="read it first"):
        _edit(executor, source)
    assert source.read_text() == "x = 1\n"

    executor.execute("read_file", {"file_path": str(source)})
    _edit(executor, source)
    assert source.read_text() == "x = 2\n"


def test_edit_rejects_stale_file(executor, source):
    executor.execute("read_file", {"file_path": str(source)})
    source.write_text("x = 1\ny = 5\n")  # changed outside the agent

    with pytest.raises(ToolError, match="changed since"):
        _edit(executor, source)

    executor.execute("read_file", {"file_path": str(source)})
    _edit(executor, source)
    assert source.read_text() == "x = 2\ny = 5\n"


def test_consecutive_edits_need_one_read(executor, source):
    executor.execute("read_file", {"file_path": str(source)})
    _edit(executor, source, "x = 1", "x = 2")
    _edit(executor, source, "x = 2", "x = 3")  # the agent knows its own change
    assert source.read_text() == "x = 3\n"


def test_overwriting_requires_read_but_new_files_do_not(executor, tmp_path, source):
    new_file = tmp_path / "new.py"
    executor.execute("write_file", {"file_path": str(new_file), "content": "a\n"})
    assert new_file.read_text() == "a\n"
    # Just written by the agent, so it may be overwritten without a read.
    executor.execute("write_file", {"file_path": str(new_file), "content": "b\n"})

    with pytest.raises(ToolError, match="read it first"):
        executor.execute("write_file", {"file_path": str(source), "content": "z\n"})


def test_paths_are_normalised(executor, source, monkeypatch):
    monkeypatch.chdir(source.parent)
    executor.execute("read_file", {"file_path": "app.py"})
    _edit(executor, source)  # absolute path, same file
    assert source.read_text() == "x = 2\n"


def test_guard_can_be_disabled(source):
    executor = ToolExecutor()
    setup_tools(executor)
    executor.require_read_before_edit = False
    _edit(executor, source)
    assert source.read_text() == "x = 2\n"


def test_prompt_has_no_duplicate_param_docs():
    prompt = get_system_prompt()
    assert "- Parameters:" not in prompt  # parameters live in the tool schemas
    assert "showing what you'll change" not in prompt  # contradicted approval modes
    assert "approval" in prompt.lower()
    assert "read" in prompt.lower() and "before" in prompt.lower()
