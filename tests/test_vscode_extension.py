"""Tests for the VS Code extension contract and structure (task 21.2)."""

import json
from pathlib import Path

from neow.cli.headless import make_interactive_approval

REPO_ROOT = Path(__file__).resolve().parent.parent
VSCODE_ROOT = REPO_ROOT / "editors" / "vscode"


def test_vscode_package_json_structure():
    pkg_path = VSCODE_ROOT / "package.json"
    assert pkg_path.exists(), f"{pkg_path} must exist"

    with open(pkg_path, "r", encoding="utf-8") as f:
        pkg = json.load(f)

    assert pkg["name"] == "neow-vscode"
    assert "version" in pkg
    assert "engines" in pkg and "vscode" in pkg["engines"]
    assert "contributes" in pkg
    contributes = pkg["contributes"]

    # Verify commands
    commands = [c["command"] for c in contributes.get("commands", [])]
    assert "neow.openChat" in commands
    assert "neow.explainSelection" in commands
    assert "neow.fixSelection" in commands
    assert "neow.applyDiff" in commands

    # Verify webview view container
    views = contributes.get("views", {})
    assert "neow-sidebar" in views
    assert any(v["id"] == "neow.chatView" for v in views["neow-sidebar"])


def test_vscode_extension_source_files_exist():
    src = VSCODE_ROOT / "src"
    assert (src / "extension.ts").exists()
    assert (src / "neowClient.ts").exists()
    assert (src / "chatViewProvider.ts").exists()
    assert (VSCODE_ROOT / "README.md").exists()
    assert (VSCODE_ROOT / "tsconfig.json").exists()


def test_interactive_approval_protocol_allow():
    from io import StringIO

    out = StringIO()
    in_ = StringIO(json.dumps({"id": 1, "approve": True}) + "\n")

    callback = make_interactive_approval(out=out, in_=in_)
    approved = callback("write_file", {"file_path": "a.py"}, "writing file")
    assert approved is True

    # Verify written event
    out.seek(0)
    lines = out.getvalue().strip().split("\n")
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["type"] == "approval_request"
    assert event["id"] == 1
    assert event["tool"] == "write_file"
    assert event["reason"] == "writing file"


def test_interactive_approval_protocol_deny():
    from io import StringIO

    out = StringIO()
    in_ = StringIO(json.dumps({"id": 1, "approve": False}) + "\n")

    callback = make_interactive_approval(out=out, in_=in_)
    approved = callback("execute_command", {"command": "rm -rf"}, "dangerous command")
    assert approved is False
