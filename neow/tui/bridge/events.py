"""TUI events emitted by the chat controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Union


@dataclass(frozen=True)
class ReasoningStarted:
    """Reasoning stream began."""


@dataclass(frozen=True)
class ReasoningDelta:
    text: str


@dataclass(frozen=True)
class ReasoningEnd:
    reasoning: str
    duration: float


@dataclass(frozen=True)
class ContentDelta:
    text: str


@dataclass(frozen=True)
class ToolStarted:
    name: str
    args: Dict[str, Any]


@dataclass(frozen=True)
class ToolFinished:
    name: str
    result: str
    is_error: bool
    denied: bool


@dataclass(frozen=True)
class TurnCompleted:
    content: str
    usage: Optional[Dict[str, int]]
    cancelled: bool


@dataclass(frozen=True)
class TurnFailed:
    message: str


TuiEvent = Union[
    ReasoningStarted,
    ReasoningDelta,
    ReasoningEnd,
    ContentDelta,
    ToolStarted,
    ToolFinished,
    TurnCompleted,
    TurnFailed,
]

__all__ = [
    "ReasoningStarted",
    "ReasoningDelta",
    "ReasoningEnd",
    "ContentDelta",
    "ToolStarted",
    "ToolFinished",
    "TurnCompleted",
    "TurnFailed",
    "TuiEvent",
]
