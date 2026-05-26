"""Command parsing for Neow CLI."""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class Command(Enum):
    """Available commands."""
    HELP = "help"
    CLEAR = "clear"
    EXIT = "exit"
    MODEL = "model"


@dataclass
class ParsedCommand:
    """Parsed command result."""
    command: Optional[Command]
    args: Optional[str] = None


def parse_command(user_input: str) -> ParsedCommand:
    """Parse user input for commands.

    Args:
        user_input: User input string.

    Returns:
        ParsedCommand object.
    """
    user_input = user_input.strip()

    if not user_input or not user_input.startswith("/"):
        return ParsedCommand(command=None)

    parts = user_input.split(maxsplit=1)
    command_str = parts[0].lower()
    args = parts[1] if len(parts) > 1 else None

    command_map = {
        "/help": Command.HELP,
        "/clear": Command.CLEAR,
        "/exit": Command.EXIT,
        "/model": Command.MODEL,
    }

    command = command_map.get(command_str)
    if command:
        return ParsedCommand(command=command, args=args)

    return ParsedCommand(command=None)
