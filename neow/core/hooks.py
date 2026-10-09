"""User-configured hooks: shell commands run at points in the agent loop.

Semantics follow Claude Code so existing hooks carry over. Configuration
(either shape works; Claude Code's event names are accepted too)::

    {"hooks": {
        "pre_tool_use": [{"matcher": "execute_command", "command": "./guard.sh",
                          "timeout": 30}],
        "PostToolUse": [{"matcher": "edit_file|write_file",
                         "hooks": [{"type": "command", "command": "ruff format ."}]}]
    }}

Events: ``session_start``, ``user_prompt_submit``, ``pre_tool_use``,
``post_tool_use`` and ``stop``. ``matcher`` is a regular expression tested
against the tool name (tool events only; empty or ``*`` matches everything).

Each command receives a JSON object on stdin (``hook_event_name``,
``session_id``, ``cwd``, plus ``prompt`` / ``tool_name`` / ``tool_input`` /
``tool_output`` as applicable). Exit codes:

- ``0``: continue. Stdout may be JSON: ``{"decision": "block", "reason": ...}``
  blocks, ``{"tool_input": {...}}`` replaces a tool's arguments
  (``pre_tool_use``). For ``user_prompt_submit`` plain stdout is added to the
  prompt as context.
- ``2``: block; stderr is the reason (shown to the model for tool events).
- anything else, or a timeout: logged as a warning; the agent continues.

``pre_tool_use`` runs before the approval prompt, so a hook can refuse a
call without asking the user. Every event is also emitted on the plugin
``EventBus`` under the same name.
"""

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from neow.utils.logger import logger

EVENTS = (
    "session_start",
    "user_prompt_submit",
    "pre_tool_use",
    "post_tool_use",
    "stop",
)
_ALIASES = {
    "SessionStart": "session_start",
    "UserPromptSubmit": "user_prompt_submit",
    "PreToolUse": "pre_tool_use",
    "PostToolUse": "post_tool_use",
    "Stop": "stop",
}
DEFAULT_TIMEOUT = 30.0
BLOCK_EXIT_CODE = 2


@dataclass
class Hook:
    command: str
    matcher: Optional["re.Pattern[str]"] = None
    timeout: float = DEFAULT_TIMEOUT

    def matches(self, tool_name: Optional[str]) -> bool:
        if self.matcher is None or tool_name is None:
            return True
        return bool(self.matcher.fullmatch(tool_name))


@dataclass
class HookOutcome:
    """Combined result of every hook that ran for one event."""

    blocked: bool = False
    reason: str = ""
    tool_input: Optional[Dict[str, Any]] = None
    context: List[str] = field(default_factory=list)


def _compile(matcher: Any, event: str) -> Optional["re.Pattern[str]"]:
    if matcher in (None, "", "*"):
        return None
    try:
        return re.compile(str(matcher))
    except re.error as exc:
        logger.warning(f"Hook {event}: invalid matcher {matcher!r}: {exc}")
        return re.compile(r"(?!)")  # matches nothing rather than everything


def parse_hooks(raw: Any) -> Dict[str, List[Hook]]:
    """Normalise the ``hooks`` config; unknown events and bad entries skipped."""
    hooks: Dict[str, List[Hook]] = {}
    if not isinstance(raw, dict):
        return hooks
    for key, entries in raw.items():
        event = _ALIASES.get(key, key)
        if event not in EVENTS:
            logger.warning(f"Unknown hook event {key!r}; expected {', '.join(EVENTS)}")
            continue
        for entry in entries if isinstance(entries, list) else [entries]:
            if not isinstance(entry, dict):
                continue
            matcher = _compile(entry.get("matcher"), event)
            # Claude Code nests the commands: {"matcher", "hooks": [{...}]}
            commands = entry.get("hooks") if "hooks" in entry else [entry]
            for command in commands or []:
                if not isinstance(command, dict) or not command.get("command"):
                    continue
                hooks.setdefault(event, []).append(
                    Hook(
                        command=str(command["command"]),
                        matcher=matcher,
                        timeout=float(command.get("timeout", DEFAULT_TIMEOUT)),
                    )
                )
    return hooks


class HookRunner:
    """Runs the configured hooks for an event and merges their decisions."""

    def __init__(
        self,
        config: Any,
        *,
        session_id: str = "",
        cwd: Optional[str] = None,
        event_bus: Any = None,
    ):
        self.hooks = parse_hooks(config)
        self.session_id = session_id
        self.cwd = cwd or os.getcwd()
        self.event_bus = event_bus

    def __bool__(self) -> bool:
        return bool(self.hooks) or self.event_bus is not None

    def run(
        self, event: str, tool_name: Optional[str] = None, **data: Any
    ) -> HookOutcome:
        payload = {
            "hook_event_name": event,
            "session_id": self.session_id,
            "cwd": self.cwd,
            **({"tool_name": tool_name} if tool_name is not None else {}),
            **data,
        }
        if self.event_bus is not None:
            self.event_bus.emit(event, **payload)
        outcome = HookOutcome()
        for hook in self.hooks.get(event, []):
            if not hook.matches(tool_name):
                continue
            if "tool_input" in payload and outcome.tool_input is not None:
                payload["tool_input"] = outcome.tool_input  # chain rewrites
            self._run_one(hook, event, payload, outcome)
            if outcome.blocked:
                break
        return outcome

    def _run_one(
        self, hook: Hook, event: str, payload: Dict[str, Any], outcome: HookOutcome
    ) -> None:
        try:
            proc = subprocess.run(
                hook.command,
                shell=True,
                input=json.dumps(payload, ensure_ascii=False, default=str),
                capture_output=True,
                text=True,
                timeout=hook.timeout,
                cwd=self.cwd,
                env={**os.environ, "NEOW_HOOK_EVENT": event},
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                f"Hook {event} timed out after {hook.timeout:.0f}s: {hook.command}"
            )
            return
        except OSError as exc:
            logger.warning(f"Hook {event} failed to start ({hook.command}): {exc}")
            return

        if proc.returncode == BLOCK_EXIT_CODE:
            outcome.blocked = True
            outcome.reason = proc.stderr.strip() or f"blocked by hook: {hook.command}"
            return
        if proc.returncode != 0:
            logger.warning(
                f"Hook {event} exited {proc.returncode} ({hook.command}): "
                f"{proc.stderr.strip()[:300]}"
            )
            return
        stdout = proc.stdout.strip()
        decision = _json_object(stdout)
        if decision is None:
            if stdout and event == "user_prompt_submit":
                outcome.context.append(stdout)
            return
        if decision.get("decision") == "block":
            outcome.blocked = True
            outcome.reason = str(decision.get("reason") or "blocked by hook")
            return
        new_input = decision.get("tool_input")
        if isinstance(new_input, dict) and event == "pre_tool_use":
            outcome.tool_input = new_input
        extra = decision.get("additional_context") or decision.get("additionalContext")
        if extra:
            outcome.context.append(str(extra))


def _json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text.startswith("{"):
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


__all__ = ["EVENTS", "Hook", "HookOutcome", "HookRunner", "parse_hooks"]
