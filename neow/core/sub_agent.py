"""Sub-agent for parallel task execution in Neow CLI."""

from typing import Any, Dict, List, Optional

from neow.core.conversation import ConversationManager
from neow.models.base import BaseModelClient
from neow.utils.logger import logger


class SubAgent:
    """An isolated sub-agent with its own conversation context.

    Each SubAgent holds an independent ConversationManager instance,
    ensuring context isolation from the main conversation and other sub-agents.
    """

    def __init__(
        self,
        model_client: BaseModelClient,
        tools: Optional[List[Dict[str, Any]]] = None,
        task_description: str = "",
        tool_executor: Optional[Any] = None,
    ):
        # Sub-agents need their own executor to avoid sharing approval state
        # with the main conversation. Clone tool functions but use yolo mode.
        from neow.core.executor import ToolExecutor
        from neow.core.approval import ApprovalMode, ApprovalPolicy

        agent_executor = ToolExecutor()
        if tool_executor:
            # Copy real tool implementations from the shared executor
            agent_executor.tools = dict(tool_executor.tools)
            agent_executor.security_guard = tool_executor.security_guard
            agent_executor.allowed_commands = list(tool_executor.allowed_commands)
            agent_executor.on_file_change = tool_executor.on_file_change

        # Sub-agents always run in yolo mode (auto-approve all tools)
        agent_executor.approval_policy = ApprovalPolicy(mode=ApprovalMode.YOLO)
        agent_executor.approval_callback = None

        self.conversation = ConversationManager(
            model_client,
            tool_executor=agent_executor,
        )
        if tools:
            self.conversation.set_tools(tools)

        system_prompt = (
            "You are a focused coding sub-agent in Neow CLI.\n"
            "You have been assigned a specific task. Complete it precisely.\n"
            f"Task: {task_description}"
        )
        self.conversation.set_system_prompt(system_prompt)
        logger.debug(f"SubAgent created: {task_description[:50]}")

    def execute(self, task: str) -> str:
        """Execute the assigned task. Returns result string."""
        logger.info(f"SubAgent executing: {task[:80]}")
        response = self.conversation.get_response(task)
        logger.info(f"SubAgent completed: {len(response.content)} chars")
        return response.content
