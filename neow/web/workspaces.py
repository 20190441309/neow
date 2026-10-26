"""Local workspace browsing and request-origin validation for Web Studio."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

DIRECTORY_LIMIT = 500
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
_HIDDEN_DIRECTORIES = {"node_modules", "__pycache__"}


def validate_workspace_path(raw: str, current: Path) -> Path:
    """Resolve an explicitly supplied absolute, existing, readable directory.

    ``current`` is deliberately not used to turn a relative path into an
    absolute one: a workspace change must identify its destination explicitly.
    This function never creates directories or changes the process cwd.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Enter an absolute workspace directory path.")
    value = raw.strip()
    if "\x00" in value:
        raise ValueError("Workspace path contains an invalid character.")
    target = Path(value)
    if not target.is_absolute():
        raise ValueError("Workspace path must be absolute.")
    try:
        target = target.resolve(strict=True)
        if not target.is_dir():
            raise ValueError("Workspace path must point to a directory.")
        with os.scandir(target):
            pass
    except (OSError, RuntimeError) as exc:
        raise ValueError(
            "Workspace directory does not exist or is not readable."
        ) from exc
    return target


def browse_workspaces(raw: str, current: Path) -> dict[str, Any]:
    """Return a bounded, alphabetically sorted listing of child directories."""
    target = validate_workspace_path(raw or str(current), current)
    directories: list[dict[str, str]] = []
    truncated = False
    try:
        with os.scandir(target) as entries:
            for entry in entries:
                if entry.name.startswith(".") or entry.name in _HIDDEN_DIRECTORIES:
                    continue
                try:
                    if not entry.is_dir():
                        continue
                    resolved = Path(entry.path).resolve(strict=True)
                except (OSError, RuntimeError):
                    continue
                if len(directories) >= DIRECTORY_LIMIT:
                    truncated = True
                    break
                directories.append({"name": entry.name, "path": str(resolved)})
    except OSError as exc:
        raise ValueError("Cannot read this directory.") from exc
    directories.sort(key=lambda item: (item["name"].casefold(), item["name"]))
    return {
        "path": str(target),
        "parent": str(target.parent) if target.parent != target else None,
        "directories": directories,
        "truncated": truncated,
    }


def _windows_local_drives() -> list[Path]:
    """Use Windows metadata only; never probe mapped network or removable drives."""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        mask = kernel32.GetLogicalDrives()
        roots = []
        for index in range(26):
            if not mask & (1 << index):
                continue
            root = f"{chr(65 + index)}:\\"
            # DRIVE_FIXED / DRIVE_RAMDISK, excluding remote and removable media.
            if kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)) in (3, 6):
                roots.append(Path(root))
        return roots
    except (AttributeError, OSError):
        return []


def workspace_roots(current: Path) -> list[dict[str, str]]:
    """Offer the current directory, home, and local drives without network probes."""
    windows = sys.platform == "win32"
    drives = _windows_local_drives() if windows else [Path("/")]
    local_anchors = {str(path).casefold() for path in drives}
    roots: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(path: Path, name: str) -> None:
        if not path.is_absolute():
            return
        text = str(path)
        key = text.casefold() if windows else text
        if key in seen:
            return
        if windows and path.anchor.casefold() not in local_anchors:
            return
        # Do not resolve/stat these shortcuts: home may be a remote profile.
        seen.add(key)
        roots.append({"name": name, "path": text})

    add(Path(current), "Current workspace")
    add(Path.home(), "Home")
    for drive in drives:
        add(drive, str(drive))
    return roots


def _parse_local_authority(value: str) -> Optional[tuple[str, int]]:
    if not isinstance(value, str) or not value:
        return None
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    if any(char in value for char in "@/\\?#%,") or value.endswith(":"):
        return None
    try:
        parsed = urlsplit(f"http://{value}")
        hostname = parsed.hostname
        port = parsed.port or 80
    except ValueError:
        return None
    if hostname not in _LOOPBACK_HOSTS or parsed.username or parsed.password:
        return None
    if parsed.path or parsed.query or parsed.fragment:
        return None
    # An explicit zero port must not be treated as the default HTTP port.
    if parsed.port == 0:
        return None
    return hostname, port


def validate_request_origin(
    host_header: Optional[str],
    origin: Optional[str],
    fetch_site: Optional[str],
    bound_host: str,
    bound_port: int,
) -> bool:
    """Accept only requests addressed to this loopback HTTP server's origin.

    A missing Origin remains valid for local CLI clients and normal same-origin
    navigation. An explicitly supplied Origin must exactly match Host, including
    its port; loopback aliases are not interchangeable browser origins.
    """
    if not isinstance(bound_host, str) or bound_host.lower() not in _LOOPBACK_HOSTS:
        return False
    if not isinstance(bound_port, int) or not 1 <= bound_port <= 65535:
        return False
    if fetch_site is not None and fetch_site not in (
        "",
        "same-origin",
        "same-site",
        "none",
    ):
        return False
    authority = _parse_local_authority(host_header)
    if authority is None or authority[1] != bound_port:
        return False
    if origin is None:
        return True
    if not isinstance(origin, str) or not origin or origin == "null":
        return False
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in origin):
        return False
    if "?" in origin or "#" in origin or "\\" in origin:
        return False
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    if parsed.scheme != "http" or parsed.path or parsed.query or parsed.fragment:
        return False
    return _parse_local_authority(parsed.netloc) == authority
