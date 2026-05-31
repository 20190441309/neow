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
    DIFF = "diff"
    COMMIT = "commit"
    UNDO = "undo"
    ADD = "add"
    DROP = "drop"
    LS = "ls"
    LINT = "lint"
    TEST = "test"
    ARCHITECT = "architect"
    CODE = "code"
    SAVE = "save"
    LOAD = "load"
    HISTORY = "history"
    COST = "cost"
    WEB = "web"
    THINK = "think"
    COMPACT = "compact"
    EXPORT = "export"
    IMAGE = "image"
    APPROVAL = "approval"
    TREE = "tree"
    BRANCH = "branch"
@dataclass
class ParsedCommand:
    """Parsed command result."""

    command: Optional[Command]
    args: Optional[str] = None
    raw_command: Optional[str] = None


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
        "/diff": Command.DIFF,
        "/commit": Command.COMMIT,
        "/undo": Command.UNDO,
        "/add": Command.ADD,
        "/drop": Command.DROP,
        "/ls": Command.LS,
        "/lint": Command.LINT,
        "/test": Command.TEST,
        "/architect": Command.ARCHITECT,
        "/code": Command.CODE,
        "/save": Command.SAVE,
        "/load": Command.LOAD,
        "/history": Command.HISTORY,
        "/cost": Command.COST,
        "/web": Command.WEB,
        "/think": Command.THINK,
        "/compact": Command.COMPACT,
        "/export": Command.EXPORT,
        "/image": Command.IMAGE,
        "/approval": Command.APPROVAL,
        "/tree": Command.TREE,
        "/branch": Command.BRANCH,
    }

    command = command_map.get(command_str)
    if command:
        return ParsedCommand(command=command, args=args)

    return ParsedCommand(command=None, args=args, raw_command=command_str)
