"""Project memory: AGENTS.md / NEOW.md (plan task 3.1)."""

from unittest.mock import MagicMock

import pytest

from neow.cli.commands import Command, parse_command
from neow.core.memory import (
    INIT_PROMPT,
    add_memory_note,
    discover_memory_files,
    load_memory,
)
from neow.tui.commands import CommandDispatcher
from tests.test_agent_loop import _conversation


@pytest.fixture
def repo(tmp_path):
    """home/ with a user file; repo/ (git root) with nested pkg/ dir."""
    home = tmp_path / "home"
    (home / ".neow").mkdir(parents=True)
    (home / ".neow" / "NEOW.md").write_text("Prefer short answers.\n")
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / "AGENTS.md").write_text("Run tests with `pytest -q`.\n")
    (root / "NEOW.md").write_text("Use uv, not pip.\n")
    pkg = root / "pkg"
    pkg.mkdir()
    (pkg / "AGENTS.md").write_text("pkg/ is generated code; do not edit.\n")
    return home, root, pkg


def test_memory_files_discovered_in_order(repo, tmp_path):
    home, root, pkg = repo
    (tmp_path / "AGENTS.md").write_text("outside the repo")  # above the git root
    found = discover_memory_files(pkg, home=home)
    assert found == [
        home / ".neow" / "NEOW.md",
        root / "AGENTS.md",
        root / "NEOW.md",
        pkg / "AGENTS.md",
    ]


def test_without_git_only_cwd_is_searched(tmp_path):
    work = tmp_path / "a" / "b"
    work.mkdir(parents=True)
    (tmp_path / "a" / "AGENTS.md").write_text("parent")
    (work / "AGENTS.md").write_text("here")
    assert discover_memory_files(work, home=tmp_path / "nohome") == [work / "AGENTS.md"]


def test_memory_text_order_and_imports(repo):
    home, root, pkg = repo
    (root / "docs").mkdir()
    (root / "docs" / "style.md").write_text("Use black, line length 88.\n")
    (root / "AGENTS.md").write_text("Run tests with `pytest -q`.\n@docs/style.md\n")
    memory = load_memory(pkg, home=home)
    text = memory.text
    order = [
        text.index("Prefer short answers"),
        text.index("pytest -q"),
        text.index("line length 88"),
        text.index("Use uv"),
        text.index("generated code"),
    ]
    assert order == sorted(order)
    assert "@docs/style.md" not in text
    assert [f.path for f in memory.files][-1] == pkg / "AGENTS.md"


def test_memory_import_depth_limit_and_cycles(tmp_path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    for i in range(8):
        (root / f"m{i}.md").write_text(f"level {i}\n@m{i + 1}.md\n")
    (root / "m8.md").write_text("level 8\n")
    (root / "AGENTS.md").write_text("TOPLEVEL\n@m0.md\n@AGENTS.md\n")  # self-import
    memory = load_memory(root, home=tmp_path / "nohome")
    assert "level 4" in memory.text and "level 5" not in memory.text
    assert memory.text.count("TOPLEVEL") == 1
    assert any("depth" in w for w in memory.warnings)


def test_emails_and_inline_at_signs_are_not_imports(repo):
    home, root, _ = repo
    (root / "AGENTS.md").write_text("Contact me@example.com or use @decorator.\n")
    text = load_memory(root, home=home).text
    assert "me@example.com" in text and "@decorator" in text


def test_total_size_limit_drops_the_most_general_first(repo):
    home, root, pkg = repo
    (home / ".neow" / "NEOW.md").write_text("U" * 5000)
    memory = load_memory(pkg, home=home, limit=300)
    assert len(memory.text) < 600
    assert "generated code" in memory.text  # the most specific file survives
    assert "UUUU" not in memory.text
    assert memory.warnings


def test_memory_in_system_prompt(repo):
    home, root, pkg = repo
    conv, client = _conversation([{"content": "ok"}])
    conv.set_system_prompt("You are Neow.")
    conv.memory = load_memory(pkg, home=home)
    systems = []
    original = client.chat_stream

    def capture(messages, system_prompt=None, tools=None):
        systems.append(system_prompt)
        yield from original(messages, system_prompt, tools)

    client.chat_stream = capture
    list(conv.get_response_stream("hi"))
    assert "Use uv, not pip." in systems[0]
    assert systems[0].index("You are Neow.") < systems[0].index("Use uv")


def test_memory_add_appends_to_project_neow_md(repo):
    home, root, pkg = repo
    path = add_memory_note(pkg, "Never touch migrations/")
    assert path == root / "NEOW.md"
    assert root.joinpath("NEOW.md").read_text().endswith("- Never touch migrations/\n")


def test_memory_command_lists_and_adds(repo, monkeypatch):
    home, root, pkg = repo
    monkeypatch.chdir(pkg)
    monkeypatch.setenv("HOME", str(home))
    conv, _ = _conversation([])
    conv.memory = load_memory(pkg, home=home)
    dispatcher = CommandDispatcher(conversation=conv)

    listing = dispatcher.dispatch(parse_command("/memory")).text
    assert "AGENTS.md" in listing and "NEOW.md" in listing

    added = dispatcher.dispatch(parse_command("/memory add Always use tabs"))
    assert added.kind != "error"
    assert "Always use tabs" in conv.memory.text  # reloaded


def test_init_generates_agents_md_via_approval():
    assert parse_command("/init").command == Command.INIT
    submitted = []
    dispatcher = CommandDispatcher(
        conversation=MagicMock(), hooks={"submit": submitted.append}
    )
    dispatcher.dispatch(parse_command("/init"))
    assert submitted == [INIT_PROMPT]
    # The agent writes the file with its normal tools, so approval applies.
    assert "AGENTS.md" in INIT_PROMPT and "create_file" in INIT_PROMPT
