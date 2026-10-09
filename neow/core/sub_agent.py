"""Sub-agents behind the ``task`` tool.

A sub-agent works on one self-contained job in a fresh context and hands
back only its final answer, which keeps long searches out of the main
conversation:

- ``explore`` sees read-only tools only, so several can run in parallel.
- ``general`` sees every tool, under the parent's approval policy; approval
  prompts are shown by the parent (labelled with the task) on its thread.

Sub-agents cannot start further sub-agents. Their token usage counts
towards the session (``/cost`` lists it separately), and cancelling the
parent turn cancels them.
"""

import copy
from typing import Any, Callable, Optional

from neow.core.agent_loop import AgentLoop
from neow.core.approval import ApprovalMode, ApprovalPolicy
from neow.core.cancellation import CancelToken, current_cancel_token
from neow.core.conversation import ConversationManager
from neow.core.executor import ToolExecutor
from neow.core.tool_context import current_channel, report_progress
from neow.utils.logger import logger

AGENT_TYPES = ("explore", "general")
DEFAULT_MAX_TURNS = 25
SUBAGENT_SOURCE = "subagent"

_ROLE = {
    "explore": (
        "You are a read-only research sub-agent. Investigate the question "
        "below with the search and read tools; you cannot change files or "
        "run commands."
    ),
    "general": (
        "You are a sub-agent handling one self-contained task for the main "
        "agent. Do the task completely, then stop."
    ),
}
_REPORT = (
    "The main agent sees only your final message, not your tool calls. End "
    "with a concise report: what you found or changed, with file paths and "
    "line numbers, and anything left undone."
)


class SubAgent:
    """One sub-agent run in a fresh conversation."""

    def __init__(
        self,
        parent: ConversationManager,
        *,
        agent_type: str = "explore",
        description: str = "",
        approval: str = "inherit",
        max_turns: int = DEFAULT_MAX_TURNS,
    ):
        if agent_type not in AGENT_TYPES:
            raise ValueError(
                f"agent_type must be one of {', '.join(AGENT_TYPES)}, "
                f"not {agent_type!r}"
            )
        self.agent_type = agent_type
        self.description = description
        executor = self._executor(parent.tool_executor, approval)
        conv = ConversationManager(
            # A copy keeps per-request client state (DeepSeek reasoning) apart
            # when several sub-agents run at once; the HTTP client is shared.
            copy.copy(parent.model_client),
            tool_executor=executor,
            token_tracker=parent.token_tracker,
        )
        conv.usage_source = SUBAGENT_SOURCE
        conv.tool_provider = executor.get_tool_definitions
        conv.memory = parent.memory
        conv.hooks = parent.hooks  # tool hooks guard sub-agents too
        conv.max_turns = max_turns
        conv.max_tool_output_chars = parent.max_tool_output_chars
        conv.set_system_prompt(
            f"{parent.system_prompt}\n\n## Sub-agent\n{_ROLE[agent_type]}\n"
            f"Task: {description}\n{_REPORT}"
        )
        self.conversation = conv

    def _executor(self, parent: ToolExecutor, approval: str) -> ToolExecutor:
        explore = self.agent_type == "explore"
        executor = ToolExecutor()
        executor.registry = parent.registry.subset(
            lambda spec: spec.name != "task" and (spec.read_only or not explore)
        )
        executor.security_guard = parent.security_guard
        executor.allowed_commands = list(parent.allowed_commands)
        executor.on_file_change = parent.on_file_change
        executor.require_read_before_edit = parent.require_read_before_edit
        if approval == "yolo":
            executor.approval_policy = ApprovalPolicy(mode=ApprovalMode.YOLO)
            return executor
        executor.approval_policy = parent.approval_policy
        executor.approval_callback = self._relayed(parent.approval_callback)
        return executor

    def _relayed(self, callback: Optional[Callable[..., bool]]):
        """Parent's approval prompt, shown on the parent loop's thread."""
        if callback is None:
            return None
        channel = current_channel()  # the parent's, captured at creation
        label = f"[子 agent · {self.description}] " if self.description else ""

        def ask(name: str, args: Any, reason: str) -> bool:
            def prompt() -> bool:
                return callback(name, args, f"{label}{reason}")

            if channel is None:
                return prompt()
            return bool(channel.call(prompt, default=False))

        return ask

    def run(self, prompt: str, cancel: Optional[CancelToken] = None) -> str:
        """Run to completion; returns the sub-agent's final message."""
        cancel = cancel or CancelToken()
        loop = AgentLoop(self.conversation, max_turns=self.conversation.max_turns)
        calls = 0
        for chunk in loop.run(prompt, cancel=cancel):
            progress = chunk.progress or {}
            if progress.get("type") == "tool_start":
                calls += 1
                step = _step(progress.get("name", ""), progress.get("args") or {})
                report_progress(f"{calls} tool call{'s' * (calls != 1)} · {step}")
        if cancel.cancelled():
            return "Error: sub-agent cancelled"
        answer = loop.result.content.strip()
        logger.info(f"Sub-agent done ({calls} tool calls): {self.description[:60]}")
        return answer or "(the sub-agent finished without a report)"


def _step(name: str, args: dict) -> str:
    for key in ("pattern", "file_path", "path", "command", "query"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return f"{name} {value[:50]}"
    return name


def run_task(
    parent: ConversationManager,
    description: str,
    prompt: str,
    agent_type: str = "explore",
) -> str:
    """Implementation of the ``task`` tool (bound per conversation)."""
    if getattr(parent, "usage_source", "main") == SUBAGENT_SOURCE:
        return "Error: sub-agents cannot start further sub-agents"
    agent = SubAgent(
        parent,
        agent_type=agent_type,
        description=description,
        approval=getattr(parent, "subagent_approval", "inherit"),
        max_turns=getattr(parent, "subagent_max_turns", DEFAULT_MAX_TURNS),
    )
    return agent.run(prompt, cancel=current_cancel_token())


__all__ = ["AGENT_TYPES", "SubAgent", "run_task"]
