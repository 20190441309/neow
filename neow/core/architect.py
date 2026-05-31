"""Architect orchestrator for planning and dispatching sub-tasks."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from neow.core.conversation import ConversationManager
from neow.core.sub_agent import SubAgent
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

MAX_SUB_TASKS = 4


class ArchitectOrchestrator:
    """Coordinates planning (strong model) and execution (fast model via sub-agents)."""

    def __init__(
        self,
        planner_client: BaseModelClient,
        executor_client: BaseModelClient,
        tool_executor: Any,
    ):
        self.planner = ConversationManager(planner_client)
        self.planner.set_system_prompt(PLANNER_SYSTEM_PROMPT)
        self.executor_client = executor_client
        self.tool_executor = tool_executor

    def run(self, user_input: str) -> str:
        """Run the architect workflow: plan, then execute sub-tasks.

        Args:
            user_input: The user's task description.

        Returns:
            Combined result from all sub-tasks, or the planner's direct answer.
        """
        plan_text = self._get_plan(user_input)
        sub_tasks = self._parse_plan(plan_text)
        if not sub_tasks:
            return plan_text
        results = self._execute_sub_tasks(sub_tasks)
        return self._summarize_results(results)

    def _get_plan(self, user_input: str) -> str:
        """Ask the planner model to decompose the task.

        Args:
            user_input: The user's task description.

        Returns:
            Planner's response text (expected to be a JSON array).
        """
        response = self.planner.get_response(user_input)
        return response.content

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

    def _execute_sub_tasks(self, sub_tasks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Execute sub-tasks in parallel using SubAgents.

        Args:
            sub_tasks: List of sub-task dicts with 'task' and 'files' keys.

        Returns:
            List of result dicts with 'task' and 'result' keys.
        """
        results = []
        with ThreadPoolExecutor(max_workers=min(len(sub_tasks), MAX_SUB_TASKS)) as executor:
            future_to_task = {}
            for sub_task in sub_tasks:
                task_desc = sub_task.get("task", "")
                files = sub_task.get("files", [])
                context = f"Focus on: {', '.join(files)}" if files else ""
                agent = SubAgent(
                    model_client=self.executor_client,
                    tools=self._get_tool_definitions(),
                    task_description=task_desc,
                    tool_executor=self.tool_executor,
                )
                future = executor.submit(agent.execute, f"{task_desc}\n{context}".strip())
                future_to_task[future] = task_desc
            for future in as_completed(future_to_task):
                task_desc = future_to_task[future]
                try:
                    result = future.result(timeout=120)
                    results.append({"task": task_desc, "result": result})
                except Exception as e:
                    logger.error(f"Sub-task failed: {e}")
                    results.append({"task": task_desc, "result": f"Error: {e}"})
        return results

    def _get_tool_definitions(self) -> list:
        """Get tool definitions for sub-agents.

        Returns:
            List of tool definition dicts.
        """
        from neow.core.prompts import get_tool_definitions
        return get_tool_definitions()

    def _summarize_results(self, results: List[Dict[str, str]]) -> str:
        """Format sub-task results into a readable summary.

        Args:
            results: List of result dicts with 'task' and 'result' keys.

        Returns:
            Formatted summary string.
        """
        if not results:
            return "No results from sub-tasks."
        if len(results) == 1:
            return results[0]["result"]
        parts = ["## Architect Mode Results\n"]
        for i, r in enumerate(results, 1):
            parts.append(f"### Sub-task {i}: {r['task']}")
            parts.append(r["result"])
            parts.append("")
        return "\n".join(parts)
