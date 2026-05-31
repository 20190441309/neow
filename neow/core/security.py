"""Security guard for Neow CLI -- command whitelist, dangerous patterns, protected files."""

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

from neow.utils.logger import logger


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
        base_cmd = command.strip().split()[0] if command.strip() else ""

        if self.is_dangerous(command):
            return SecurityCheck(
                allowed=False,
                reason=f"Dangerous command detected: {command}",
            )

        if allowed_commands and base_cmd not in allowed_commands:
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
            if fnmatch.fnmatch(file_name, pattern) or fnmatch.fnmatch(file_path, pattern):
                logger.warning(f"Protected file access attempt: {file_path}")
                return True
        return False
