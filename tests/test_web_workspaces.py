"""Workspace helpers are read-only and never trust cross-origin requests."""

from pathlib import Path

import pytest

from neow.web import workspaces


def test_validate_workspace_requires_an_existing_absolute_directory(tmp_path):
    assert (
        workspaces.validate_workspace_path(str(tmp_path), tmp_path)
        == tmp_path.resolve()
    )
    for value in ("", " ", ".", "relative/project", "bad\x00path"):
        with pytest.raises(ValueError):
            workspaces.validate_workspace_path(value, tmp_path)
    missing = tmp_path / "missing"
    with pytest.raises(ValueError):
        workspaces.validate_workspace_path(str(missing), tmp_path)
    assert not missing.exists()
    file_path = tmp_path / "file.txt"
    file_path.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ValueError):
        workspaces.validate_workspace_path(str(file_path), tmp_path)


def test_validate_workspace_reports_unreadable_directory(tmp_path, monkeypatch):
    def refuse(_path):
        raise PermissionError("denied")

    monkeypatch.setattr(workspaces.os, "scandir", refuse)
    with pytest.raises(ValueError, match="not readable"):
        workspaces.validate_workspace_path(str(tmp_path), tmp_path)


def test_browse_lists_only_visible_directories_in_name_order(tmp_path):
    for name in ("zebra", "Alpha", "beta", ".git", "node_modules", "__pycache__"):
        (tmp_path / name).mkdir()
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    result = workspaces.browse_workspaces("", tmp_path)
    assert result["path"] == str(tmp_path.resolve())
    assert result["parent"] == str(tmp_path.parent.resolve())
    assert [item["name"] for item in result["directories"]] == [
        "Alpha",
        "beta",
        "zebra",
    ]
    assert all(Path(item["path"]).is_absolute() for item in result["directories"])
    assert result["truncated"] is False


def test_browse_is_bounded_and_marks_truncation(tmp_path, monkeypatch):
    monkeypatch.setattr(workspaces, "DIRECTORY_LIMIT", 2)
    for name in ("a", "b", "c"):
        (tmp_path / name).mkdir()
    result = workspaces.browse_workspaces(str(tmp_path), tmp_path)
    assert len(result["directories"]) == 2
    assert result["truncated"] is True


def test_workspace_roots_do_not_probe_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(
        workspaces, "_windows_local_drives", lambda: [Path(tmp_path.anchor)]
    )

    def refuse(*_args, **_kwargs):
        raise AssertionError("Root shortcuts must not probe the filesystem")

    monkeypatch.setattr(Path, "stat", refuse)
    monkeypatch.setattr(Path, "resolve", refuse)
    result = workspaces.workspace_roots(tmp_path)
    assert result
    assert result[0] == {"name": "Current workspace", "path": str(tmp_path)}
    assert len({item["path"] for item in result}) == len(result)


@pytest.mark.parametrize(
    ("host", "origin", "fetch_site"),
    [
        ("127.0.0.1:7860", "http://127.0.0.1:7860", "same-origin"),
        ("localhost:7860", "http://localhost:7860", "same-origin"),
        ("[::1]:7860", "http://[::1]:7860", "same-origin"),
        ("LOCALHOST:7860", "http://localhost:7860", "same-origin"),
        ("127.0.0.1:7860", None, None),
        ("localhost:7860", None, "none"),
    ],
)
def test_origin_accepts_loopback_same_origin(host, origin, fetch_site):
    assert workspaces.validate_request_origin(
        host, origin, fetch_site, "127.0.0.1", 7860
    )


@pytest.mark.parametrize(
    ("host", "origin", "fetch_site"),
    [
        ("evil.example:7860", None, None),
        ("127.0.0.1:7861", None, None),
        ("127.0.0.1", None, None),
        ("127.0.0.1:7860", "null", "same-origin"),
        ("127.0.0.1:7860", "", "same-origin"),
        ("127.0.0.1:7860", "http://evil.example:7860", "cross-site"),
        ("127.0.0.1:7860", "http://127.0.0.1:7860", "cross-site"),
        ("127.0.0.1:7860", None, "cross-site"),
        ("127.0.0.1:7860", "http://localhost:7860", "same-site"),
        ("127.0.0.1:7860", "https://127.0.0.1:7860", "same-site"),
        ("127.0.0.1:7860", "http://127.0.0.1:9999", "same-site"),
        ("127.0.0.1:7860", "http://user@127.0.0.1:7860", None),
        ("127.0.0.1:7860", "http://127.0.0.1:7860/path", None),
        ("127.0.0.1:7860", "http://127.0.0.1:7860?query=yes", None),
        ("127.0.0.1:7860", "http://127.0.0.1:7860#fragment", None),
        ("127.0.0.1:7860", " http://127.0.0.1:7860", None),
        ("127.0.0.1:7860", "http://127.0.0.1:7860\r\n", None),
        ("user@127.0.0.1:7860", None, None),
        ("127.0.0.1:7860/", None, None),
        ("127.0.0.1:7860\\", None, None),
        ("127.0.0.1:7860\r\nInjected: yes", None, None),
        ("localhost.:7860", None, None),
        ("0.0.0.0:7860", None, None),
        ("127.0.0.1:0", None, None),
        ("127.0.0.1:65536", None, None),
        ("[::1", None, None),
        (None, None, None),
    ],
)
def test_origin_rejects_untrusted_or_malformed_requests(host, origin, fetch_site):
    assert not workspaces.validate_request_origin(
        host, origin, fetch_site, "127.0.0.1", 7860
    )


def test_origin_rejects_wildcard_bound_host():
    assert not workspaces.validate_request_origin(
        "127.0.0.1:7860", None, None, "0.0.0.0", 7860
    )


def test_default_http_port_is_supported():
    assert workspaces.validate_request_origin(
        "localhost", "http://localhost", None, "localhost", 80
    )
