"""Architect mode: a planner model writes the plan, the main agent carries it out.

The planner (usually a stronger model) turns the request into steps, which
become the conversation's task list. The main agent then works through them
one at a time with its normal tools and approvals; it may hand research to
read-only ``explore`` sub-agents, but nothing edits files in parallel.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from neow.core.conversation import ConversationManager
from neow.models.base import BaseModelClient
from neow.utils.logger import logger

PLANNER_SYSTEM_PROMPT = """You are an architect agent in Neow CLI.
Your job is to analyze the user's task and break it into sub-tasks.

Output ONLY a JSON array of sub-tasks. Each sub-task has:
- "task": detailed description of what to do
- "files": list of relevant file paths

Example:
[
  {"task": "Read main.py and identify the import error on line 5", "files": ["main.py"]},
  {"task": "Fix the import by adding the missing import statement", "files": ["main.py"]}
]

If the task is simple and doesn't need decomposition, output a single-element array.
Output ONLY the JSON array, no other text."""

MAX_SUB_TASKS = 8


class ArchitectOrchestrator:
    """Plans with *planner_client*; execution happens in the main conversation."""

    def __init__(self, planner_client: BaseModelClient, memory: Optional[Any] = None):
        self.planner = ConversationManager(planner_client)
        self.planner.set_system_prompt(PLANNER_SYSTEM_PROMPT)
        self.planner.memory = memory

    def plan(self, user_input: str) -> Tuple[List[Dict[str, str]], str]:
        """``(todos, planner text)``; no todos when the planner answered directly."""
        text = self.planner.get_response(user_input).content
        steps = self._parse_plan(text)
        todos = []
        for index, step in enumerate(steps, 1):
            task = str(step.get("task", "")).strip() if isinstance(step, dict) else ""
            if not task:
                continue
            files = step.get("files") or []
            if files:
                task += f" (files: {', '.join(map(str, files))})"
            todos.append({"id": str(index), "content": task, "status": "pending"})
        return todos, text

    @staticmethod
    def execution_prompt(user_input: str, todos: List[Dict[str, str]]) -> str:
        """Message that asks the main agent to carry out the plan."""
        steps = "\n".join(f"{i}. {t['content']}" for i, t in enumerate(todos, 1))
        return (
            f"{user_input}\n\n"
            "A planner has broken this request into the steps below; they are "
            "already in your task list. Work through them in order: mark each "
            "step in_progress with todo_write before starting it and completed "
            "when done. For research that needs many reads you may use the task "
            "tool with agent_type 'explore'. Adjust the plan if a step turns "
            "out to be wrong.\n\n"
            f"Plan:\n{steps}"
        )

    def _parse_plan(self, plan_text: str) -> List[Dict[str, Any]]:
        """Parse the planner's response into a list of sub-tasks.

        Handles JSON wrapped in markdown code fences.

        Args:
            plan_text: Raw text from the planner.

        Returns:
            List of sub-task dicts, or empty list if parsing fails.
        """
        text = plan_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```") and not in_block:
                    in_block = True
                    continue
                elif line.startswith("```") and in_block:
                    break
                elif in_block:
                    json_lines.append(line)
            text = "\n".join(json_lines)
        try:
            plan = json.loads(text)
            if isinstance(plan, list) and len(plan) > 0:
                return plan[:MAX_SUB_TASKS]
        except json.JSONDecodeError:
            logger.debug("Planner response is not valid JSON, treating as direct answer")
        return []
