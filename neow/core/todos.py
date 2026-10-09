"""Task list the agent keeps for multi-step work (the ``todo_write`` tool).

Each call replaces the whole list. Items are plain dicts so they survive
session save/restore unchanged: ``{"id", "content", "status"}``.
"""

import json
from typing import Any, Dict, List

STATUSES = ("pending", "in_progress", "completed")
MARKS = {"pending": "☐", "in_progress": "▶", "completed": "☑"}


class TodoError(ValueError):
    """The submitted list is malformed."""


def validate_todos(todos: Any) -> List[Dict[str, str]]:
    """Normalised copy of *todos*, or :class:`TodoError` explaining the problem."""
    if isinstance(todos, str):  # some models send the array as a JSON string
        try:
            todos = json.loads(todos)
        except ValueError as exc:
            raise TodoError(f"todos must be an array: {exc}") from exc
    if not isinstance(todos, list):
        raise TodoError("todos must be an array of {id, content, status}")
    items: List[Dict[str, str]] = []
    seen = set()
    for index, raw in enumerate(todos, 1):
        if not isinstance(raw, dict):
            raise TodoError(f"todo #{index} must be an object")
        content = str(raw.get("content") or "").strip()
        if not content:
            raise TodoError(f"todo #{index} has no content")
        status = raw.get("status", "pending")
        if status not in STATUSES:
            raise TodoError(
                f"todo #{index} has status {status!r}; use one of "
                f"{', '.join(STATUSES)}"
            )
        todo_id = str(raw.get("id") or index)
        if todo_id in seen:
            raise TodoError(f"duplicate todo id {todo_id!r}")
        seen.add(todo_id)
        items.append({"id": todo_id, "content": content, "status": status})
    active = [t["id"] for t in items if t["status"] == "in_progress"]
    if len(active) > 1:
        raise TodoError(
            f"only one todo may be in_progress at a time (got {', '.join(active)})"
        )
    return items


def format_todos(todos: List[Dict[str, str]]) -> str:
    """Compact plain-text checklist."""
    if not todos:
        return "(no todos)"
    return "\n".join(f"{MARKS[t['status']]} {t['content']}" for t in todos)


def todo_summary(todos: List[Dict[str, str]]) -> str:
    done = sum(t["status"] == "completed" for t in todos)
    return f"{done}/{len(todos)} done"


__all__ = [
    "MARKS",
    "STATUSES",
    "TodoError",
    "format_todos",
    "todo_summary",
    "validate_todos",
]
