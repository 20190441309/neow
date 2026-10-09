"""grep / glob / list_dir tools (plan task 4.1)."""

import json
import os
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from neow.tools import fs_search
from neow.tools.fs_search import SearchToolError, glob, glob_match, grep, list_dir

_REAL_WHICH = shutil.which  # the fixtures patch shutil.which


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A git repo with an ignored directory, an untracked file and a binary."""
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "dist").mkdir()
    (root / ".gitignore").write_text("dist/\n*.log\n")
    (root / "src" / "app.py").write_text("import os\n\ndef main():\n    return 1\n")
    (root / "src" / "pkg" / "util.py").write_text("def helper():\n    pass\n")
    (root / "src" / "pkg" / "ui.ts").write_text("export function main() {}\n")
    (root / "README.md").write_text("# Demo\nRun main() to start.\n")
    (root / "dist" / "bundle.py").write_text("def main(): pass\n")
    (root / "debug.log").write_text("main crashed\n")
    (root / "data.bin").write_bytes(b"\0main\0")
    _git(root, "init", "-q")
    _git(root, "add", ".")
    (root / "notes.txt").write_text("untracked main\n")  # untracked, not ignored
    monkeypatch.chdir(root)
    monkeypatch.setattr(fs_search.shutil, "which", lambda name: None)
    return root


def test_grep_python_fallback_respects_gitignore(repo):
    out = grep("main")
    assert out.splitlines() == ["README.md", "notes.txt", "src/app.py", "src/pkg/ui.ts"]


def test_grep_outside_git_skips_build_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(fs_search.shutil, "which", lambda name: None)
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("needle\n")
    (tmp_path / "a.py").write_text("needle\n")
    monkeypatch.chdir(tmp_path)
    assert grep("needle") == "a.py"


def test_grep_content_mode_with_context(repo):
    out = grep("def main", path="src", output_mode="content", context=1)
    assert out.splitlines() == [
        "src/app.py-2-",
        "src/app.py:3:def main():",
        "src/app.py-4-    return 1",
    ]


def test_grep_count_glob_case_and_limit(repo):
    assert grep("MAIN", case_insensitive=True, output_mode="count", glob="*.py") == (
        "src/app.py:1"
    )
    assert grep("main", glob="src/**/*.{ts,tsx}") == "src/pkg/ui.ts"
    limited = grep("main", head_limit=2)
    assert limited.splitlines()[:2] == ["README.md", "notes.txt"]
    assert "showing 2 of 4 files" in limited


def test_grep_single_file_and_errors(repo):
    assert grep("helper", path="src/pkg/util.py") == "src/pkg/util.py"
    assert grep("nothing-like-this") == "No matches found"
    with pytest.raises(SearchToolError, match="Invalid regex"):
        grep("(")
    with pytest.raises(SearchToolError, match="not found"):
        grep("x", path="missing")
    with pytest.raises(SearchToolError, match="output_mode"):
        grep("x", output_mode="lines")


def _rg_event(kind, path, line, text):
    return json.dumps(
        {
            "type": kind,
            "data": {
                "path": {"text": path},
                "lines": {"text": text + "\n"},
                "line_number": line,
            },
        }
    )


def test_grep_uses_ripgrep_when_available(repo, monkeypatch):
    calls = []
    real_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if cmd[0] != "/usr/bin/rg":
            return real_run(cmd, **kwargs)
        calls.append(cmd)
        stdout = "\n".join(
            [
                json.dumps({"type": "begin", "data": {}}),
                _rg_event("context", "./src/app.py", 2, ""),
                _rg_event("match", "./src/app.py", 3, "def main():"),
            ]
        ).encode()
        return SimpleNamespace(returncode=0, stdout=stdout, stderr=b"")

    monkeypatch.setattr(fs_search.shutil, "which", lambda name: "/usr/bin/rg")
    monkeypatch.setattr(fs_search.subprocess, "run", fake_run)
    out = grep("def main", output_mode="content", context=1, glob="*.py")
    assert out.splitlines() == ["src/app.py-2-", "src/app.py:3:def main():"]
    cmd = calls[0]
    assert "--json" in cmd and ["--glob", "*.py"] == cmd[cmd.index("*.py") - 1:][:2]
    assert cmd[-1] == "." and "--context" in cmd
    assert "!node_modules" not in cmd  # inside git, .gitignore decides


def test_grep_falls_back_when_ripgrep_fails(repo, monkeypatch):
    real_run = subprocess.run

    def broken_rg(cmd, **kwargs):
        if cmd[0] == "/usr/bin/rg":
            return SimpleNamespace(returncode=2, stdout=b"", stderr=b"boom")
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(fs_search.shutil, "which", lambda name: "/usr/bin/rg")
    monkeypatch.setattr(fs_search.subprocess, "run", broken_rg)
    assert grep("helper") == "src/pkg/util.py"


@pytest.mark.skipif(_REAL_WHICH("rg") is None, reason="ripgrep not installed")
def test_ripgrep_and_fallback_agree(repo, monkeypatch):
    monkeypatch.setattr(fs_search.shutil, "which", _REAL_WHICH)
    with_rg = grep("main", output_mode="content")
    monkeypatch.setattr(fs_search.shutil, "which", lambda name: None)
    assert grep("main", output_mode="content") == with_rg


def test_glob_sorted_by_mtime(repo):
    for i, name in enumerate(["src/app.py", "src/pkg/util.py", "README.md"]):
        os.utime(repo / name, (1_000_000 + i, 1_000_000 + i))
    assert glob("**/*.py").splitlines() == ["src/pkg/util.py", "src/app.py"]
    assert glob("*.md") == "README.md"  # no '/': top level only
    assert glob("src/*.py") == "src/app.py"
    assert glob("*.log") == "No files found"  # ignored by git
    assert glob("*.py", path="src") == "src/app.py"


def test_glob_match_rules():
    assert glob_match("a/b/c.py", "**/*.py")
    assert glob_match("c.py", "**/*.py")
    assert not glob_match("a/c.py", "*.py")
    assert glob_match("src/x.tsx", "src/*.{ts,tsx}")
    assert glob_match("f1.txt", "f[0-9].txt") and not glob_match("fa.txt", "f[!a].txt")


def test_list_dir_depth(repo):
    assert list_dir().splitlines() == [
        "./",
        "  src/",
        "  .gitignore",
        "  data.bin",
        "  notes.txt",
        "  README.md",
    ]
    deep = list_dir(depth=3).splitlines()
    assert "    pkg/" in deep and "      util.py" in deep and "    app.py" in deep
    assert list_dir("src", depth=1).splitlines() == ["src/", "  pkg/", "  app.py"]
    with pytest.raises(SearchToolError, match="Not a directory"):
        list_dir("README.md")


def test_tools_are_registered_read_only():
    from neow.core.approval import ApprovalTier
    from neow.tools.builtin import builtin_specs

    specs = {spec.name: spec for spec in builtin_specs()}
    for name in ("grep", "glob", "list_dir"):
        assert specs[name].read_only and specs[name].tier == ApprovalTier.READ
    assert specs["search_code"].description.startswith("Deprecated")
