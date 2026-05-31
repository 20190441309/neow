"""Command execution tools for Neow CLI."""

import re
import shutil
import subprocess
import sys
from typing import Optional

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


def execute_command(command: str, timeout: int = 30, cwd: Optional[str] = None) -> str:
    """Execute a shell command.

    On Windows, PowerShell is preferred because it ships with aliases for
    common Unix commands (``ls``, ``cat``, ``grep``, …).  Unix-style
    commands and flags are automatically translated to native PowerShell
    cmdlet syntax.  When PowerShell is not available, a best-effort
    translation table maps Unix commands to their ``cmd.exe`` equivalents.

    Args:
        command: Command to execute.
        timeout: Timeout in seconds (default 30).
        cwd: Working directory (optional).

    Returns:
        Command output as string.

    Raises:
        CommandError: If command fails or times out.
    """
    try:
        logger.debug(f"Executing command: {command}")

        if sys.platform == "win32":
            shell_path = _get_shell_for_windows()
            if shell_path:
                # Translate Unix commands to PowerShell cmdlet syntax
                translated = _translate_for_powershell(command)
                logger.debug(f"PowerShell command: {translated}")
                result = subprocess.run(
                    [shell_path, "-NoProfile", "-Command", translated],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=cwd,
                )
            else:
                # Fallback: translate common Unix commands for cmd.exe
                translated = _translate_unix_command(command)
                result = subprocess.run(
                    translated,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=cwd,
                )
        else:
            # Unix: use shell=True (invokes /bin/sh)
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )

        if result.returncode != 0:
            error_msg = (
                result.stderr or f"Command failed with return code {result.returncode}"
            )
            logger.debug(f"Command failed: {error_msg}")
            return f"Error: {error_msg}"

        logger.debug(f"Command output: {result.stdout[:100]}...")
        return result.stdout

    except subprocess.TimeoutExpired:
        logger.debug(f"Command timed out after {timeout} seconds")
        return f"Error: Command timed out after {timeout} seconds"
    except Exception as e:
        logger.debug(f"Command execution failed: {e}")
        return f"Error: {e}"
