"""Conversation manager for Neow CLI."""

from typing import Any, Dict, List, Optional

from neow.models.base import BaseModelClient, ModelResponse
from neow.utils.logger import logger


class ConversationManager:
    """Manages conversation history and AI model interactions."""

    def __init__(self, model_client: BaseModelClient):
        """Initialize conversation manager.

        Args:
            model_client: AI model client instance.
        """
        self.model_client = model_client
        self.messages: List[Dict[str, str]] = []
        self.system_prompt: str = ""
        self.tools: List[Dict[str, Any]] = []

    def set_system_prompt(self, prompt: str) -> None:
        """Set system prompt.

        Args:
            prompt: System prompt text.
        """
        self.system_prompt = prompt
        logger.debug(f"System prompt set ({len(prompt)} chars)")

    def set_tools(self, tools: List[Dict[str, Any]]) -> None:
        """Set available tools.

        Args:
            tools: List of tool definitions.
        """
        self.tools = tools
        logger.debug(f"Set {len(tools)} tools")

    def add_message(self, role: str, content: str) -> None:
        """Add message to conversation history.

        Args:
            role: Message role (user, assistant, tool).
            content: Message content.
        """
        self.messages.append({"role": role, "content": content})
        logger.debug(f"Added {role} message ({len(content)} chars)")

    def get_response(self, user_input: str) -> ModelResponse:
        """Get AI response for user input.

        Args:
            user_input: User input text.

        Returns:
            ModelResponse object.
        """
        # Add user message
        self.add_message("user", user_input)

        # Get response from model
        response = self.model_client.chat(
            messages=self.messages,
            system_prompt=self.system_prompt if self.system_prompt else None,
            tools=self.tools if self.tools else None
        )

        # Add assistant message
        self.add_message("assistant", response.content)

        logger.info(
            f"Response generated ({response.usage.get('total_tokens', 0)} tokens)"
        )

        return response

    def add_tool_result(self, tool_call_id: str, result: str) -> None:
        """Add tool result to conversation history.

        Args:
            tool_call_id: Tool call ID.
            result: Tool execution result.
        """
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result
        })
        logger.debug(f"Added tool result for {tool_call_id}")

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.messages.clear()
        logger.debug("Conversation history cleared")

    def get_history(self) -> List[Dict[str, str]]:
        """Get conversation history.

        Returns:
            List of message dictionaries.
        """
        return self.messages.copy()
