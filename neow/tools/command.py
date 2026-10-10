"""Command execution tools for Neow CLI."""

import os
import re
import shutil
import signal
import subprocess
import sys
import time
from typing import Optional

from neow.core.cancellation import current_cancel_token
from neow.tools import sandbox
from neow.utils.logger import logger


class CommandError(Exception):
    """Command execution error."""

    pass


# Common Unix commands and their Windows cmd.exe equivalents (fallback only).
_UNIX_CMD_MAP = {
    "ls": "dir",
    "cat": "type",
    "grep": "findstr",
    "rm": "del",
    "cp": "copy",
    "mv": "move",
    "pwd": "cd",
    "which": "where",
    "touch": "type nul >",
    "clear": "cls",
    "head": "more",
    "tail": "more",
    "find": "dir /s /b",
    "chmod": "icacls",
    "chown": "icacls",
}


def _get_shell_for_windows() -> Optional[str]:
    """Return the path to the best available shell on Windows.

    Prefers PowerShell Core (pwsh) which supports ``&&``, ``||``, and
    Unix-style aliases.  Falls back to Windows PowerShell.  Returns
    ``None`` when neither is found (very rare on Windows 10+).
    """
    for name in ("pwsh", "powershell"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _translate_for_powershell(command: str) -> str:
    """Translate common Unix commands to native PowerShell cmdlets.

    PowerShell ships aliases like ``ls`` → ``Get-ChildItem`` and ``cat``
    → ``Get-Content``, but these cmdlets do **not** accept Unix-style
    flags (``-la``, ``-n``, etc.).  This function rewrites the command
    to use the native cmdlet syntax so that ``ls -la`` becomes
    ``Get-ChildItem -Force`` and ``grep -r pattern .`` becomes
    ``Get-ChildItem -Recurse | Select-String pattern``.
    """
    parts = command.split(None, 1)
    if not parts:
        return command
    base = parts[0]
    rest = parts[1] if len(parts) > 1 else ""

    # ── ls → Get-ChildItem ──────────────────────────────────────────
    if base in ("ls", "dir"):
        flags = _extract_flags(rest)
        args = _strip_flags(rest)
        ps_flags = []
        if "l" in flags or "a" in flags:
            ps_flags.append("-Force")
        if "R" in flags or "r" in flags:
            ps_flags.append("-Recurse")
        cmd = "Get-ChildItem"
        if ps_flags:
            cmd += " " + " ".join(ps_flags)
        if args:
            cmd += " " + args
        return cmd

    # ── cat → Get-Content ───────────────────────────────────────────
    if base == "cat":
        flags = _extract_flags(rest)
        args = _strip_flags(rest)
        ps_flags = []
        if "n" in flags:
            ps_flags.append("")  # Get-Content numbers by default
        cmd = "Get-Content"
        if ps_flags:
            cmd += " " + " ".join(f for f in ps_flags if f)
        if args:
            cmd += " " + args
        return cmd

    # ── grep → Select-String ────────────────────────────────────────
    if base == "grep":
        flags = _extract_flags(rest)
        args = _strip_flags(rest)
        ps_flags = []
        if "i" in flags:
            ps_flags.append("-CaseSensitive:$false")
        if "r" in flags or "R" in flags:
            # Select-String with -Path needs a recurse approach
            # Simplify: extract pattern and path from args
            arg_parts = args.split(None, 1)
            pattern = arg_parts[0] if arg_parts else ""
            path = arg_parts[1] if len(arg_parts) > 1 else "."
            cmd = f'Get-ChildItem -Recurse -File {path} | Select-String {pattern}'
            if "i" in flags:
                cmd += " -CaseSensitive:$false"
            return cmd
        cmd = "Select-String"
        if ps_flags:
            cmd += " " + " ".join(ps_flags)
        if args:
            cmd += " " + args
        return cmd

    # ── rm → Remove-Item ────────────────────────────────────────────
    if base == "rm":
        flags = _extract_flags(rest)
        args = _strip_flags(rest)
        ps_flags = []
        if "r" in flags or "R" in flags:
            ps_flags.append("-Recurse")
        if "f" in flags:
            ps_flags.append("-Force")
        cmd = "Remove-Item"
        if ps_flags:
            cmd += " " + " ".join(ps_flags)
        if args:
            cmd += " " + args
        return cmd

    # ── cp → Copy-Item ──────────────────────────────────────────────
    if base in ("cp", "copy"):
        flags = _extract_flags(rest)
        args = _strip_flags(rest)
        ps_flags = []
        if "r" in flags or "R" in flags:
            ps_flags.append("-Recurse")
        cmd = "Copy-Item"
        if ps_flags:
            cmd += " " + " ".join(ps_flags)
        if args:
            cmd += " " + args
        return cmd

    # ── mv → Move-Item ──────────────────────────────────────────────
    if base in ("mv", "move"):
        args = _strip_flags(rest)
        cmd = "Move-Item"
        if args:
            cmd += " " + args
        return cmd

    # ── mkdir → New-Item ────────────────────────────────────────────
    if base == "mkdir":
        flags = _extract_flags(rest)
        args = _strip_flags(rest)
        cmd = "New-Item -ItemType Directory"
        if args:
            cmd += " " + args
        return cmd

    # ── touch → New-Item ────────────────────────────────────────────
    if base == "touch":
        args = _strip_flags(rest)
        cmd = "New-Item -ItemType File"
        if args:
            cmd += " " + args
        return cmd

    # ── find → Get-ChildItem ────────────────────────────────────────
    if base == "find":
        args = _strip_flags(rest)
        cmd = "Get-ChildItem -Recurse"
        if args:
            cmd += " " + args
        return cmd

    # ── head → Select-Object ────────────────────────────────────────
    if base == "head":
        flags = _extract_flags(rest)
        args = _strip_flags(rest)
        n = "10"
        n_match = re.search(r"(\d+)", args)
        if "n" in flags and n_match:
            n = n_match.group(1)
        cmd = f"Select-Object -First {n}"
        return cmd

    # ── tail → Select-Object ────────────────────────────────────────
    if base == "tail":
        flags = _extract_flags(rest)
        args = _strip_flags(rest)
        n = "10"
        n_match = re.search(r"(\d+)", args)
        if "n" in flags and n_match:
            n = n_match.group(1)
        cmd = f"Select-Object -Last {n}"
        return cmd

    # ── which → Get-Command ─────────────────────────────────────────
    if base in ("which", "where"):
        args = _strip_flags(rest)
        cmd = "Get-Command"
        if args:
            cmd += " " + args
        return cmd

    # ── pwd → Get-Location ──────────────────────────────────────────
    if base == "pwd":
        return "Get-Location"

    # ── echo → Write-Output ─────────────────────────────────────────
    if base == "echo":
        args = _strip_flags(rest)
        cmd = "Write-Output"
        if args:
            cmd += " " + args
        return cmd

    # ── env → Get-ChildItem Env: ────────────────────────────────────
    if base == "env":
        return "Get-ChildItem Env:"

    # ── No translation needed ───────────────────────────────────────
    return command


def _extract_flags(rest: str) -> str:
    """Extract combined short flags like ``-la`` or ``-rn``.

    Returns a string of flag characters without dashes, e.g. ``"la"``.
    """
    flags = ""
    for m in re.finditer(r"-([a-zA-Z]+)", rest):
        chunk = m.group(1)
        # Skip long flags like --help or --recursive
        if len(chunk) > 1 and chunk[0].isupper() == chunk[0].islower():
            continue  # single letter flags only, skip --long-flags
        if len(chunk) == 1 or chunk.isalpha():
            flags += chunk
    return flags.lower()


def _strip_flags(rest: str) -> str:
    """Remove short flags (``-x``, ``-xyz``) from *rest*, keep args."""
    return re.sub(r"\s*-[a-zA-Z]+\b", "", rest).strip()


def _translate_unix_command(command: str) -> str:
    """Translate a common Unix command to its Windows cmd.exe equivalent.

    Only the *first* word is translated; flags and arguments are left
    untouched.  This is a best-effort fallback when PowerShell is not
    available.
    """
    parts = command.split(None, 1)
    if not parts:
        return command
    base = parts[0].lower()
    if base in _UNIX_CMD_MAP:
        replacement = _UNIX_CMD_MAP[base]
        return f"{replacement} {parts[1]}" if len(parts) > 1 else replacement
    return command


DEFAULT_TIMEOUT = 120
_max_timeout = 600
POLL_INTERVAL = 0.1
KILL_GRACE = 1.0


def configure(*, max_timeout: Optional[int] = None) -> None:
    """Apply ``tools.command`` settings from the config."""
    global _max_timeout
    if max_timeout:
        _max_timeout = int(max_timeout)


def effective_timeout(timeout: Optional[int]) -> int:
    """Requested timeout, defaulted and capped at the configured maximum."""
    if not timeout or timeout <= 0:
        return DEFAULT_TIMEOUT
    return min(int(timeout), _max_timeout)


def _spawn(
    command: str, cwd: Optional[str], argv: Optional[list] = None
) -> subprocess.Popen:
    """Start *command* in its own process group so it can be killed whole.

    *argv*, when given, is the sandboxed command line (see ``sandbox``).
    """
    options = dict(
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        cwd=cwd,
    )
    if sys.platform == "win32":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        shell_path = _get_shell_for_windows()
        if shell_path:
            # Translate Unix commands to PowerShell cmdlet syntax
            translated = _translate_for_powershell(command)
            logger.debug(f"PowerShell command: {translated}")
            return subprocess.Popen(
                [shell_path, "-NoProfile", "-Command", translated], **options
            )
        # Fallback: translate common Unix commands for cmd.exe
        return subprocess.Popen(_translate_unix_command(command), shell=True, **options)
    # Unix: /bin/sh in a new session (= new process group)
    if argv:
        return subprocess.Popen(argv, start_new_session=True, **options)
    return subprocess.Popen(command, shell=True, start_new_session=True, **options)


def _terminate(proc: subprocess.Popen) -> None:
    """Stop the whole process tree: polite signal first, then force."""
    if sys.platform == "win32":
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
            proc.wait(KILL_GRACE)
        except Exception:
            pass
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True
        )
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(KILL_GRACE)
        except subprocess.TimeoutExpired:
            continue
    # The shell is gone; make sure nothing it started survives it.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _with_output(message: str, stdout: str, stderr: str) -> str:
    output = (stdout or "") + (stderr or "")
    return f"{message}\n{output}".rstrip() if output.strip() else message


def _noted(note: str, result: str) -> str:
    """Prefix a sandbox fallback note, keeping a leading ``Error:`` first."""
    if not note:
        return result
    if result.startswith("Error:"):
        head, _, rest = result.partition("\n")
        return f"{head}\n{note}\n{rest}".rstrip()
    return f"{note}\n{result}"


def execute_command(
    command: str, timeout: int = DEFAULT_TIMEOUT, cwd: Optional[str] = None
) -> str:
    """Execute a shell command.

    On Windows, PowerShell is preferred because it ships with aliases for
    common Unix commands (``ls``, ``cat``, ``grep``, …).  Unix-style
    commands and flags are automatically translated to native PowerShell
    cmdlet syntax.  When PowerShell is not available, a best-effort
    translation table maps Unix commands to their ``cmd.exe`` equivalents.

    The command runs in its own process group.  It is killed, together
    with everything it started, on timeout or when the current turn's
    :class:`~neow.core.cancellation.CancelToken` is cancelled (Esc).

    Args:
        command: Command to execute.
        timeout: Timeout in seconds (default 120, capped by
            ``tools.command.max_timeout``).
        cwd: Working directory (optional).

    Returns:
        stdout (plus stderr) on success; ``Error: ...`` with the exit code
        and both streams on failure, timeout or cancellation.
    """
    timeout = effective_timeout(timeout)
    token = current_cancel_token()
    logger.debug(f"Executing command: {command}")
    argv, note = (None, "") if sys.platform == "win32" else sandbox.plan(command, cwd)
    if note.startswith("Error:"):
        return note
    try:
        proc = _spawn(command, cwd, argv)
    except Exception as e:
        logger.debug(f"Command execution failed: {e}")
        return f"Error: {e}"

    deadline = time.monotonic() + timeout
    while True:
        try:
            stdout, stderr = proc.communicate(timeout=POLL_INTERVAL)
            break
        except subprocess.TimeoutExpired:
            if token is not None and token.cancelled():
                message = "Error: cancelled by user"
            elif time.monotonic() >= deadline:
                message = f"Error: Command timed out after {timeout} seconds"
            else:
                continue
        logger.debug(f"{message}: {command}")
        _terminate(proc)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
        return _noted(note, _with_output(message, stdout, stderr))

    if proc.returncode != 0:
        logger.debug(f"Command failed with exit code {proc.returncode}")
        return _noted(
            note, _with_output(f"Error: exit code {proc.returncode}", stdout, stderr)
        )

    logger.debug(f"Command output: {stdout[:100]}...")
    if stderr and stderr.strip():
        return _noted(note, f"{stdout}{stderr}")
    return _noted(note, stdout)
