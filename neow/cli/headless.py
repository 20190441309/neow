"""Headless runs for scripts and CI: ``neow -p "..." --output-format json``.

Formats:

- ``text``: the final reply on stdout.
- ``json``: one object when the run ends::

      {"type": "result", "result": "...", "is_error": false, "session_id": "...",
       "num_turns": 3, "usage": {...}, "cost": 0.0123, "duration_ms": 8120,
       "model": "..."}

- ``stream-json``: one JSON object per line as the agent works: an ``init``
  line, then one line per agent-loop event (``content_delta``,
  ``reasoning_delta``, ``tool_start``, ``tool_progress``, ``tool_end``,
  ``notice``, ``usage``, …), and the same ``result`` object last.

Tools that need approval are refused (the model is told so) unless the run
uses ``--approval yolo``, or ``--approval-interactive`` (requires
``--output-format stream-json``), which opens an ``approval_request``/
stdin-reply channel instead (see ``make_interactive_approval`` — this is
what an editor/IDE integration, task 21, drives to show an allow/deny
dialog).

Exit codes: 0 success, 1 the model request failed, 2 bad arguments (from
click), 130 interrupted.
"""

import fnmatch
import itertools
import json
import os
import sys
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, TextIO

from neow.core.agent_loop import AgentLoop, CancelToken
from neow.core.executor import ToolDenied

OUTPUT_FORMATS = ("text", "json", "stream-json")
EXIT_OK, EXIT_ERROR, EXIT_INTERRUPTED = 0, 1, 130


def parse_tool_list(value: Optional[str]) -> List[str]:
    """``"read_file, grep mcp__*"`` -> names / glob patterns."""
    if not value:
        return []
    return [p for p in value.replace(",", " ").split() if p]


def filter_tools(
    registry: Any, allowed: Iterable[str] = (), disallowed: Iterable[str] = ()
) -> List[str]:
    """Remove tools not in *allowed* (if given) or in *disallowed*.

    Patterns may use ``*`` (``mcp__github__*``). Returns the removed names.
    """
    allowed, disallowed = list(allowed), list(disallowed)

    def matches(name: str, patterns: List[str]) -> bool:
        return any(fnmatch.fnmatchcase(name, p) for p in patterns)

    removed = []
    for name in registry.names():
        if (allowed and not matches(name, allowed)) or matches(name, disallowed):
            registry.unregister(name)
            removed.append(name)
    return removed


def refuse_approval(name: str, args: Any, reason: str) -> bool:
    """Approval callback for headless runs: nobody can answer."""
    raise ToolDenied(
        f"{name} needs approval, which is not possible in a headless run "
        f"({reason}). Use read-only tools, or the user can rerun with "
        "--approval yolo."
    )


def make_interactive_approval(
    out: Optional[TextIO] = None, in_: Optional[TextIO] = None
) -> Callable[[str, Dict[str, Any], str], bool]:
    """Approval callback for ``--output-format stream-json``: ask over the pipe.

    Writes one ``approval_request`` line to *out* and blocks for one reply
    line on *in_* — the shape an editor/IDE integration (task 21) drives: it
    reads stream-json events, shows a dialog for ``approval_request``, and
    writes the decision back on stdin::

        {"type": "approval_request", "id": 1, "tool": "write_file",
         "args": {...}, "reason": "..."}
        -> stdin: {"id": 1, "approve": true}

    A closed pipe, unparseable reply, or mismatched id denies the call
    (fail safe) rather than hanging or approving something unintended.
    """
    out = out or sys.stdout
    in_ = in_ or sys.stdin
    request_id = itertools.count(1)

    def callback(name: str, args: Dict[str, Any], reason: str) -> bool:
        this_id = next(request_id)
        out.write(
            json.dumps(
                {"type": "approval_request", "id": this_id, "tool": name, "args": args, "reason": reason},
                ensure_ascii=False,
                default=str,
            )
            + "\n"
        )
        out.flush()
        line = in_.readline()
        if not line:
            return False
        try:
            decision = json.loads(line)
        except json.JSONDecodeError:
            return False
        return decision.get("id") == this_id and bool(decision.get("approve"))

    return callback


def _event(chunk: Any) -> Optional[Dict[str, Any]]:
    """A stream chunk as a stream-json event (``None`` for nothing to say)."""
    if chunk.progress:
        return dict(chunk.progress)
    if chunk.content_delta:
        return {"type": "content_delta", "text": chunk.content_delta}
    if chunk.reasoning_delta:
        return {"type": "reasoning_delta", "text": chunk.reasoning_delta}
    if chunk.usage:
        return {"type": "usage", **chunk.usage}
    return None


def _usage(tracker: Any) -> Dict[str, int]:
    if tracker is None:
        return {}
    return {
        "input_tokens": tracker.session_input,
        "output_tokens": tracker.session_output,
        "cache_read_tokens": tracker.session_cache_read,
        "cache_write_tokens": tracker.session_cache_write,
    }


def run_headless(
    conversation: Any,
    prompt: str,
    output_format: str = "text",
    *,
    out: TextIO = None,
    save_session: Any = None,
) -> int:
    """Run one prompt to completion; returns the process exit code.

    *save_session* (optional) is called after the run and returns the
    session name reported as ``session_id``.
    """
    out = out or sys.stdout
    stream = output_format == "stream-json"
    model = getattr(conversation.model_client, "model", "unknown")

    def emit(obj: Dict[str, Any]) -> None:
        out.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
        out.flush()

    if stream:
        tools = [d["function"]["name"] for d in conversation._tool_definitions() or []]
        emit({"type": "init", "model": model, "tools": tools, "cwd": os.getcwd()})

    started = time.monotonic()
    cancel = CancelToken()
    loop = AgentLoop(conversation, max_turns=conversation.max_turns)
    error = ""
    code = EXIT_OK
    try:
        for chunk in loop.run(prompt, cancel=cancel):
            if stream:
                event = _event(chunk)
                if event is not None:
                    emit(event)
    except KeyboardInterrupt:
        cancel.cancel()
        error, code = "interrupted", EXIT_INTERRUPTED
    except Exception as exc:  # the model request failed
        error, code = str(exc) or type(exc).__name__, EXIT_ERROR

    session_id = ""
    if save_session is not None:
        try:
            session_id = save_session() or ""
        except Exception:  # noqa: BLE001 - never hide the result
            session_id = ""
    result = loop.result.content or ""
    if output_format == "text":
        if result:
            out.write(result + ("" if result.endswith("\n") else "\n"))
        if error:
            sys.stderr.write(f"Error: {error}\n")
        return code
    tracker = getattr(conversation, "token_tracker", None)
    emit(
        {
            "type": "result",
            "result": error if error and not result else result,
            "is_error": bool(error),
            "session_id": session_id,
            "num_turns": loop.requests,
            "usage": _usage(tracker),
            "cost": round(tracker.get_session_cost(), 6) if tracker else 0.0,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "model": model,
        }
    )
    return code


__all__ = [
    "OUTPUT_FORMATS",
    "filter_tools",
    "parse_tool_list",
    "refuse_approval",
    "run_headless",
]
