"""Conversation manager for Neow CLI."""

import json
from typing import Any, Dict, List, Optional

from neow.models.base import BaseModelClient, ModelResponse
from neow.utils.logger import logger


def _sanitize_text(text: str) -> str:
    """Remove surrogate characters that cause encoding errors."""
    return text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")


class ConversationManager:
    """Manages conversation history and AI model interactions."""

    def __init__(
        self, model_client: BaseModelClient, tool_executor: Optional[Any] = None
    ):
        """Initialize conversation manager.

        Args:
            model_client: AI model client instance.
            tool_executor: Optional tool executor for handling tool calls.
                If not provided, a default ToolExecutor will be created.
        """
        self.model_client = model_client
        if tool_executor is None:
            from neow.core.executor import ToolExecutor

            self.tool_executor = ToolExecutor()
        else:
            self.tool_executor = tool_executor
        self.messages: List[Dict[str, Any]] = []
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

        Handles tool calls by executing them and getting follow-up responses.

        Args:
            user_input: User input text.

        Returns:
            ModelResponse object.
        """
        # Add user message
        self.add_message("user", user_input)

        # Sanitize messages to remove surrogate characters
        sanitized_messages = []
        for msg in self.messages:
            sanitized_msg = {k: _sanitize_text(v) if isinstance(v, str) else v for k, v in msg.items()}
            sanitized_messages.append(sanitized_msg)

        # Get response from model
        response = self.model_client.chat(
            messages=sanitized_messages,
            system_prompt=self.system_prompt if self.system_prompt else None,
            tools=self.tools if self.tools else None,
        )

        # Handle tool calls if present
        while response.has_tool_calls and self.tool_executor:
            # Format tool_calls with type field for API compatibility
            formatted_tool_calls = []
            for tc in response.tool_calls:
                formatted_tc = {
                    "id": tc["id"],
                    "type": "function",
                    "function": tc["function"],
                }
                formatted_tool_calls.append(formatted_tc)

            # Add assistant message with tool calls
            # Include reasoning_content if available (for DeepSeek thinking mode)
            assistant_msg = {
                "role": "assistant",
                "content": response.content,
                "tool_calls": formatted_tool_calls,
            }
            # Check if model client has stored reasoning_content
            if hasattr(self.model_client, '_last_reasoning_content') and self.model_client._last_reasoning_content:
                assistant_msg["reasoning_content"] = self.model_client._last_reasoning_content

            self.messages.append(assistant_msg)

            # Execute each tool call
            for tool_call in response.tool_calls:
                tool_name = tool_call["function"]["name"]
                arguments = json.loads(tool_call["function"]["arguments"])

                try:
                    result = self.tool_executor.execute(tool_name, arguments)
                except Exception as e:
                    result = f"Error: {e}"

                # Add tool result to messages
                self.add_tool_result(tool_call["id"], result)

            # Get next response from model
            # Sanitize messages before sending
            sanitized_messages = []
            for msg in self.messages:
                sanitized_msg = {k: _sanitize_text(v) if isinstance(v, str) else v for k, v in msg.items()}
                sanitized_messages.append(sanitized_msg)

            # Debug: log messages being sent
            logger.debug(f"Sending {len(sanitized_messages)} messages to model")
            for i, msg in enumerate(sanitized_messages):
                logger.debug(f"Message {i}: role={msg.get('role')}, keys={list(msg.keys())}")

            response = self.model_client.chat(
                messages=sanitized_messages,
                system_prompt=self.system_prompt if self.system_prompt else None,
                tools=self.tools if self.tools else None,
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
        # Note: DeepSeek API requires 'type' field for tool messages
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": _sanitize_text(str(result)),
                "type": "tool_result",
            }
        )
        logger.debug(f"Added tool result for {tool_call_id}")

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.messages.clear()
        logger.debug("Conversation history cleared")

    def get_history(self) -> List[Dict[str, Any]]:
        """Get conversation history.

        Returns:
            List of message dictionaries.
        """
        return self.messages.copy()
