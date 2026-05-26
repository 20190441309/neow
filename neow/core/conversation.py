"""Conversation manager for Neow CLI."""

import json
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from neow.models.base import BaseModelClient, ModelResponse, StreamChunk
from neow.utils.logger import logger

FILE_MUTATING_TOOLS = {"write_file", "edit_file", "create_file", "delete_file"}


def _sanitize_text(text: str) -> str:
    """Remove surrogate characters that cause encoding errors."""
    return text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")


class ConversationManager:
    """Manages conversation history and AI model interactions."""

    def __init__(
        self,
        model_client: BaseModelClient,
        tool_executor: Optional[Any] = None,
        context_manager: Optional[Any] = None,
        token_tracker: Optional[Any] = None,
    ):
        """Initialize conversation manager.

        Args:
            model_client: AI model client instance.
            tool_executor: Optional tool executor for handling tool calls.
                If not provided, a default ToolExecutor will be created.
            context_manager: Optional ContextManager for project context injection.
            token_tracker: Optional TokenTracker for usage tracking.
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
        self.context_files: Dict[str, str] = {}  # abs_path -> content
        self.context_manager = context_manager
        self.token_tracker = token_tracker
        self._structure_injected = False
        self.web_cache: Dict[str, Any] = {}  # url -> WebContent
        self.pending_lint_feedback: Optional[str] = None

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
            system_prompt=self._get_effective_system_prompt(user_input),
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

                # Auto-refresh context files after file mutations
                if tool_name in FILE_MUTATING_TOOLS:
                    edited_path = arguments.get("file_path", "")
                    if edited_path:
                        abs_path = str(Path(edited_path).resolve())
                        if abs_path in self.context_files:
                            if tool_name == "delete_file":
                                del self.context_files[abs_path]
                            else:
                                self.refresh_context_file(abs_path)

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
                system_prompt=self._get_effective_system_prompt(user_input),
                tools=self.tools if self.tools else None,
            )

        # Add assistant message
        self.add_message("assistant", response.content)

        # Record token usage
        if self.token_tracker and response.usage:
            self.token_tracker.record(response.usage, getattr(self.model_client, 'model', 'unknown'))

        logger.info(
            f"Response generated ({response.usage.get('total_tokens', 0)} tokens)"
        )

        return response

    def get_response_stream(self, user_input: str) -> Generator[StreamChunk, None, None]:
        """Get streaming AI response for user input.

        Args:
            user_input: User input text.

        Yields:
            StreamChunk objects.
        """
        self.add_message("user", user_input)

        while True:
            sanitized_messages = []
            for msg in self.messages:
                sanitized_msg = {k: _sanitize_text(v) if isinstance(v, str) else v for k, v in msg.items()}
                sanitized_messages.append(sanitized_msg)

            content_buffer = ""
            tool_calls_final = None
            usage_final = {}

            for chunk in self.model_client.chat_stream(
                messages=sanitized_messages,
                system_prompt=self._get_effective_system_prompt(user_input),
                tools=self.tools if self.tools else None,
            ):
                if chunk.content_delta:
                    content_buffer += chunk.content_delta
                if chunk.tool_call_delta:
                    tool_calls_final = chunk.tool_call_delta.get("tool_calls")
                if chunk.usage:
                    usage_final = chunk.usage
                yield chunk

            response = ModelResponse(
                content=content_buffer,
                tool_calls=tool_calls_final or [],
                usage=usage_final,
            )

            if not response.has_tool_calls or not self.tool_executor:
                break

            # Execute tools silently
            formatted_tool_calls = []
            for tc in response.tool_calls:
                formatted_tool_calls.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": tc["function"],
                })

            assistant_msg = {
                "role": "assistant",
                "content": response.content,
                "tool_calls": formatted_tool_calls,
            }
            if hasattr(self.model_client, '_last_reasoning_content') and self.model_client._last_reasoning_content:
                assistant_msg["reasoning_content"] = self.model_client._last_reasoning_content
            self.messages.append(assistant_msg)

            for tool_call in response.tool_calls:
                tool_name = tool_call["function"]["name"]
                arguments = json.loads(tool_call["function"]["arguments"])
                try:
                    result = self.tool_executor.execute(tool_name, arguments)
                except Exception as e:
                    result = f"Error: {e}"

                # Auto-refresh context files after file mutations
                if tool_name in FILE_MUTATING_TOOLS:
                    edited_path = arguments.get("file_path", "")
                    if edited_path:
                        abs_path = str(Path(edited_path).resolve())
                        if abs_path in self.context_files:
                            if tool_name == "delete_file":
                                del self.context_files[abs_path]
                            else:
                                self.refresh_context_file(abs_path)

                self.add_tool_result(tool_call["id"], result)

        self.add_message("assistant", response.content)

        # Record token usage
        if self.token_tracker and usage_final:
            self.token_tracker.record(usage_final, getattr(self.model_client, 'model', 'unknown'))

        logger.info(f"Streamed response ({response.usage.get('total_tokens', 0)} tokens)")

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

    def add_context_file(self, file_path: str) -> str:
        """Add a file to the conversation context.

        Args:
            file_path: Path to the file.

        Returns:
            Confirmation message.

        Raises:
            FileNotFoundError: If file doesn't exist.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        content = path.read_text(encoding="utf-8")
        abs_path = str(path.resolve())
        self.context_files[abs_path] = content
        logger.info(f"Added context file: {file_path} ({len(content)} chars)")
        return f"Added to context: {file_path} ({len(content)} chars)"

    def drop_context_file(self, file_path: str) -> str:
        """Remove a file from the conversation context.

        Args:
            file_path: Path or name of the file.

        Returns:
            Confirmation message.

        Raises:
            KeyError: If file not in context.
        """
        abs_path = str(Path(file_path).resolve())
        if abs_path in self.context_files:
            del self.context_files[abs_path]
            return f"Removed from context: {file_path}"
        # Try matching by filename
        for key in list(self.context_files.keys()):
            if key.endswith(file_path) or Path(key).name == file_path:
                del self.context_files[key]
                return f"Removed from context: {file_path}"
        raise KeyError(f"File not in context: {file_path}")

    def list_context_files(self) -> List[str]:
        """List files in the conversation context.

        Returns:
            List of file paths.
        """
        return list(self.context_files.keys())

    def add_web_content(self, url: str, content: Any) -> None:
        """Cache fetched web content for context injection.

        Args:
            url: The source URL.
            content: WebContent instance.
        """
        self.web_cache[url] = content
        logger.info(f"Cached web content: {url} ({len(content.text)} chars)")

    def refresh_context_file(self, file_path: str) -> bool:
        """Re-read a context file to pick up external changes.

        Args:
            file_path: Path to the file.

        Returns:
            True if refreshed, False if not in context.
        """
        abs_path = str(Path(file_path).resolve())
        if abs_path in self.context_files:
            try:
                self.context_files[abs_path] = Path(abs_path).read_text(encoding="utf-8")
                return True
            except (FileNotFoundError, UnicodeDecodeError):
                return False
        return False

    def _build_context_prompt(self) -> str:
        """Build context files portion of system prompt.

        Returns:
            Formatted string with context file contents.
        """
        parts = []

        # Context files
        if self.context_files:
            parts.append("\n## Context Files\n")
            parts.append("The following files have been explicitly added to the conversation context:\n")
            for path, content in self.context_files.items():
                parts.append(f"### {path}")
                parts.append("```")
                parts.append(content)
                parts.append("```\n")

        # Web content
        if self.web_cache:
            parts.append("\n## Web Content\n")
            parts.append("The following web pages have been fetched into context:\n")
            for url, content in self.web_cache.items():
                parts.append(f"### {content.title} ({url})")
                parts.append(content.text)
                if content.code_blocks:
                    for lang, code in content.code_blocks:
                        parts.append(f"```{lang}")
                        parts.append(code)
                        parts.append("```")
                parts.append("")

        return "\n".join(parts)

    def _build_project_context(self, user_input: str = "") -> str:
        """Build project context portion of system prompt.

        Args:
            user_input: The user's input for matching relevant files.

        Returns:
            Formatted project context string, or empty string.
        """
        if not self.context_manager:
            return ""
        from neow.core.prompts import format_project_context

        parts = []
        if not self._structure_injected:
            structure = self.context_manager.get_project_structure(max_depth=2)
            parts.append(format_project_context(structure, []))
            self._structure_injected = True
        if user_input:
            relevant = self.context_manager.get_relevant_files(user_input)
            if relevant:
                parts.append(format_project_context({}, relevant))
        return "\n".join(parts)

    def _get_effective_system_prompt(self, user_input: str = "") -> Optional[str]:
        """Get system prompt including context files and project context.

        Args:
            user_input: The user's input for matching relevant files.

        Returns:
            Combined system prompt, or None if empty.
        """
        prompt = self.system_prompt
        context_prompt = self._build_context_prompt()
        if context_prompt:
            prompt += context_prompt
        project_context = self._build_project_context(user_input)
        if project_context:
            prompt += project_context
        return prompt if prompt else None
