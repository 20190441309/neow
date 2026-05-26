"""Command execution tools for Neow CLI."""

import subprocess
from typing import Optional

from neow.utils.logger import logger


class CommandError(Exception):
    """Command execution error."""

    pass


def execute_command(command: str, timeout: int = 30, cwd: Optional[str] = None) -> str:
    """Execute a shell command.

    Args:
        command: Command to execute.
        timeout: Timeout in seconds (default: 30).
        cwd: Working directory (optional).

    Returns:
        Command output as string.

    Raises:
        CommandError: If command fails or times out.
    """
    try:
        logger.debug(f"Executing command: {command}")

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
            logger.error(f"Command failed: {error_msg}")
            raise CommandError(error_msg)

        logger.debug(f"Command output: {result.stdout[:100]}...")
        return result.stdout

    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout} seconds")
        raise CommandError(f"Command timed out after {timeout} seconds")
    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        raise CommandError(f"Command execution failed: {e}")
