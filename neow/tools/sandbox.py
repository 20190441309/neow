"""Optional sandbox for shell commands run by the agent (experimental).

``tools.command.sandbox`` selects the mode:

- ``off`` (default): commands run normally.
- ``auto``: sandbox when possible; otherwise run normally and say so.
- ``strict``: refuse to run a command that cannot be sandboxed.

Inside the sandbox the whole file system is read-only except the project
(the git root, or the working directory), the system temp directory and any
``tools.command.sandbox_writable`` paths, and there is no network unless
``tools.command.sandbox_network`` is true.

Linux uses bubblewrap (``bwrap``); macOS uses ``sandbox-exec``. Windows has
no sandbox.
"""

import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

MODES = ("off", "auto", "strict")


@dataclass
class SandboxConfig:
    mode: str = "off"
    network: bool = False
    writable: List[str] = field(default_factory=list)
    bwrap: str = ""  # explicit path; default: bwrap on PATH


_config = SandboxConfig()
_warned = False


def configure(
    mode: Optional[str] = None,
    network: Optional[bool] = None,
    writable: Optional[List[str]] = None,
    bwrap: Optional[str] = None,
) -> SandboxConfig:
    """Apply ``tools.command`` settings; unknown modes fall back to off."""
    global _config, _warned
    _config = SandboxConfig(
        mode=mode if mode in MODES else "off",
        network=bool(network),
        writable=[str(Path(p).expanduser()) for p in writable or []],
        bwrap=bwrap or "",
    )
    _warned = False
    return _config


def current() -> SandboxConfig:
    return _config


def _project_dir(cwd: str) -> str:
    from neow.core.memory import project_root

    return str(project_root(Path(cwd)))


def _writable_dirs(cwd: str) -> List[str]:
    dirs = [_project_dir(cwd), cwd, tempfile.gettempdir(), *_config.writable]
    seen, result = set(), []
    for directory in dirs:
        real = os.path.realpath(directory)
        if real not in seen and os.path.isdir(real):
            seen.add(real)
            result.append(real)
    return result


def _bwrap_argv(command: str, cwd: str) -> Optional[List[str]]:
    binary = _config.bwrap or shutil.which("bwrap")
    if not binary:
        return None
    argv = [
        binary,
        "--ro-bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
    ]
    for directory in _writable_dirs(cwd):
        argv += ["--bind", directory, directory]
    if not _config.network:
        argv.append("--unshare-net")
    argv += [
        "--die-with-parent",
        "--chdir",
        os.path.realpath(cwd),
        "/bin/sh",
        "-c",
        command,
    ]
    return argv


def _seatbelt_profile(cwd: str) -> str:
    rules = ["(version 1)", "(allow default)", "(deny file-write*)"]
    paths = " ".join(f'(subpath "{d}")' for d in _writable_dirs(cwd))
    rules.append(
        f'(allow file-write* {paths} (subpath "/private/var/folders") '
        '(literal "/dev/null") (literal "/dev/tty"))'
    )
    if not _config.network:
        rules.append("(deny network*)")
    return "\n".join(rules)


def _macos_argv(command: str, cwd: str) -> Optional[List[str]]:
    binary = shutil.which("sandbox-exec")
    if not binary:
        return None
    return [binary, "-p", _seatbelt_profile(cwd), "/bin/sh", "-c", command]


def sandbox_argv(
    command: str, cwd: Optional[str] = None, platform: Optional[str] = None
) -> Tuple[Optional[List[str]], str]:
    """``(argv, "")`` to run *command* sandboxed, or ``(None, reason)``."""
    cwd = cwd or os.getcwd()
    platform = platform or sys.platform
    if platform.startswith("linux"):
        argv = _bwrap_argv(command, cwd)
        return argv, "" if argv else "bwrap (bubblewrap) is not installed"
    if platform == "darwin":
        argv = _macos_argv(command, cwd)
        return argv, "" if argv else "sandbox-exec is not available"
    return None, f"no sandbox is available on {platform}"


def plan(command: str, cwd: Optional[str] = None) -> Tuple[Optional[List[str]], str]:
    """How to run *command* under the configured mode.

    Returns ``(argv, note)``: ``argv`` is the sandboxed command line, or
    ``None`` to run it normally. ``note`` is a message for the output (a
    fallback warning in ``auto``) or, when it starts with ``Error:``, the
    reason the command must not run (``strict``).
    """
    global _warned
    if _config.mode == "off":
        return None, ""
    argv, reason = sandbox_argv(command, cwd)
    if argv is not None:
        return argv, ""
    if _config.mode == "strict":
        return None, (
            f"Error: sandbox required (tools.command.sandbox: strict) but "
            f"{reason}; the command was not run"
        )
    if _warned:
        return None, ""
    _warned = True
    return None, f"[sandbox unavailable: {reason}; running without it]"


def status(cwd: Optional[str] = None) -> str:
    """One line for approval prompts: will a command run sandboxed?"""
    if _config.mode == "off":
        return ""
    argv, reason = sandbox_argv("true", cwd)
    if argv is None:
        return (
            "will not run (sandbox unavailable)"
            if _config.mode == "strict"
            else f"not sandboxed: {reason}"
        )
    network = "network allowed" if _config.network else "no network"
    return f"sandboxed: writes limited to the project and temp dir, {network}"


__all__ = ["MODES", "configure", "current", "plan", "sandbox_argv", "status"]
