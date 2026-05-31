"""Conversation manager for Neow CLI."""

import json
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from neow.models.base import BaseModelClient, ModelResponse, StreamChunk
from neow.utils import sanitize_text as _sanitize_text
from neow.utils.logger import logger
FILE_MUTATING_TOOLS = {"write_file", "edit_file", "create_file", "delete_file"}


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
        self._pending_images: List[Dict[str, Any]] = []  # queued images for next message

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

    def queue_image(self, image_path: str) -> str:
        """Queue an image to be included in the next user message.

        Args:
            image_path: Path to the image file.

        Returns:
            Confirmation message.

        Raises:
            FileNotFoundError: If image file doesn't exist.
        """
        import base64
        import mimetypes

        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        mime_type = mimetypes.guess_type(str(path))[0] or "image/png"
        if not mime_type.startswith("image/"):
            raise ValueError(f"Not an image file: {image_path}")

        with open(path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")

        self._pending_images.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": image_data,
            },
        })
        logger.info(f"Queued image: {image_path} ({mime_type})")
        return f"Image queued: {path.name} ({mime_type})"

    def _build_vision_content(self, text: str) -> Any:
        """Build message content with optional pending images.

        Args:
            text: The text content of the message.

        Returns:
            String if no images, list of content blocks if images pending.
        """
        if not self._pending_images:
            return text

        content = [{"type": "text", "text": text}]
        content.extend(self._pending_images)
        self._pending_images.clear()
        return content
    def get_response(self, user_input: str) -> ModelResponse:
        """Get AI response for user input.

        Handles tool calls by executing them and getting follow-up responses.

        Args:
            user_input: User input text.

        Returns:
            ModelResponse object.
        """
        # Add user message
        content = self._build_vision_content(user_input)
        self.messages.append({"role": "user", "content": content})
        logger.debug(f"Added user message ({len(user_input)} chars)")

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
            assistant_msg = {
                "role": "assistant",
                "content": response.content,
                "tool_calls": formatted_tool_calls,
            }
            # DeepSeek thinking mode: reasoning_content must be passed back
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

        # Add assistant message (with reasoning_content for DeepSeek thinking mode)
        final_msg: Dict[str, Any] = {"role": "assistant", "content": response.content}
        if hasattr(self.model_client, '_last_reasoning_content') and self.model_client._last_reasoning_content:
            final_msg["reasoning_content"] = self.model_client._last_reasoning_content
        self.messages.append(final_msg)
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
        vision_content = self._build_vision_content(user_input)
        self.messages.append({"role": "user", "content": vision_content})

        while True:
            sanitized_messages = []
            for msg in self.messages:
                sanitized_msg = {k: _sanitize_text(v) if isinstance(v, str) else v for k, v in msg.items()}
                sanitized_messages.append(sanitized_msg)

            content_buffer = ""
            tool_calls_final = None
            usage_final = {}
            reasoning_active = False

            for chunk in self.model_client.chat_stream(
                messages=sanitized_messages,
                system_prompt=self._get_effective_system_prompt(user_input),
                tools=self.tools if self.tools else None,
            ):
                if chunk.reasoning_delta:
                    if not reasoning_active:
                        reasoning_active = True
                        yield StreamChunk(progress={"type": "reasoning_start"})
                if chunk.content_delta and reasoning_active:
                    reasoning_active = False
                    yield StreamChunk(progress={"type": "reasoning_end"})

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

            # Execute tools with progress notification
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
            # DeepSeek thinking mode: reasoning_content must be passed back
            if hasattr(self.model_client, '_last_reasoning_content') and self.model_client._last_reasoning_content:
                assistant_msg["reasoning_content"] = self.model_client._last_reasoning_content
            self.messages.append(assistant_msg)

            for tool_call in response.tool_calls:
                tool_name = tool_call["function"]["name"]
                arguments = json.loads(tool_call["function"]["arguments"])

                yield StreamChunk(progress={"type": "tool_start", "name": tool_name, "args": arguments})
                try:
                    result = self.tool_executor.execute(tool_name, arguments)
                except Exception as e:
                    result = f"Error: {e}"
                yield StreamChunk(progress={"type": "tool_end", "name": tool_name, "result": result[:500]})

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
        # Add final assistant message
        final_msg: Dict[str, Any] = {"role": "assistant", "content": response.content}
        if hasattr(self.model_client, '_last_reasoning_content') and self.model_client._last_reasoning_content:
            final_msg["reasoning_content"] = self.model_client._last_reasoning_content
        self.messages.append(final_msg)

        # Record token usage
        if self.token_tracker and usage_final:
            self.token_tracker.record(usage_final, getattr(self.model_client, 'model', 'unknown'))

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

    def compact(self) -> str:
        """Summarize conversation history to free context window space.

        Replaces the message history with a condensed summary while
        preserving the system prompt and context files.

        Returns:
            Summary of what was compressed.
        """
        # Extract user/assistant text messages only (skip tool calls/results)
        text_messages = []
        for msg in self.messages:
            role = msg.get("role")
            if role in ("user", "assistant") and msg.get("content"):
                text_messages.append(f"{role}: {msg['content']}")

        if not text_messages:
            return "Nothing to compact."

        conversation_text = "\n".join(text_messages)
        msg_count = len(self.messages)

        # Ask the model to summarize
        summary_prompt = (
            "Summarize the following conversation into a concise context "
            "that preserves all key decisions, file changes made, bugs fixed, "
            "and current task state. Be factual and terse.\n\n"
            f"{conversation_text}"
        )

        response = self.model_client.chat(
            messages=[{"role": "user", "content": _sanitize_text(summary_prompt)}],
            system_prompt="You are a conversation summarizer. Output only the summary, no preamble.",
        )

        # Safety: summarizer should not return tool_calls, but guard against it
        if response.has_tool_calls:
            logger.warning("Summarizer returned tool_calls, ignoring")

        summary = response.content

        # Replace history with summary
        self.messages.clear()
        self.messages.append({
            "role": "user",
            "content": "[Context was compacted to save tokens]",
        })
        self.messages.append({
            "role": "assistant",
            "content": summary,
        })

        # Record the summary tokens
        if self.token_tracker and response.usage:
            self.token_tracker.record(response.usage, getattr(self.model_client, 'model', 'unknown'))

        logger.info(f"Compacted {msg_count} messages into summary ({len(summary)} chars)")
        return f"Compacted {msg_count} messages → {len(summary)} char summary"

    def compact_incremental(self, keep_recent_tokens: int = 4000) -> str:
        """Incrementally compact old messages while preserving recent context.

        Only summarizes messages older than the recent N estimated tokens,
        keeping the most recent messages intact for continuity.

        Args:
            keep_recent_tokens: Approximate number of recent tokens to preserve.
                Estimated as ~4 chars per token.

        Returns:
            Summary of what was compressed.
        """
        if len(self.messages) <= 4:
            return "Too few messages to compact."

        # Estimate token boundary: walk backward from end to find split point
        chars_per_token = 4
        keep_chars = keep_recent_tokens * chars_per_token
        recent_char_count = 0
        split_idx = len(self.messages)

        for i in range(len(self.messages) - 1, -1, -1):
            msg = self.messages[i]
            content = msg.get("content", "")
            if isinstance(content, str):
                recent_char_count += len(content)
            if recent_char_count >= keep_chars:
                split_idx = i + 1
                break
        else:
            # All messages fit within keep_recent_tokens
            return "Recent context fits within keep_recent_tokens. Nothing to compact."

        if split_idx <= 2:
            return "Too few old messages to compact."

        # Split-turn preservation: never split in the middle of a tool-call turn.
        # If the first "recent" message is a tool result (role=tool), move the
        # split point back to include the assistant message that initiated it.
        while split_idx > 1 and self.messages[split_idx - 1].get("role") == "tool":
            split_idx -= 1
        # Also ensure we don't leave a bare tool_calls assistant without its results
        if split_idx < len(self.messages) and self.messages[split_idx - 1].get("tool_calls"):
            # The assistant message at split_idx-1 has tool_calls but its results
            # would be in the "recent" section — move it all to recent
            split_idx -= 1

        if split_idx <= 2:
            return "Too few old messages to compact after turn alignment."

        # Split: old messages [0..split_idx) to summarize, recent [split_idx..) to keep
        old_messages = self.messages[:split_idx]
        recent_messages = self.messages[split_idx:]
        # Extract text from old messages
        text_messages = []
        for msg in old_messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role in ("user", "assistant") and isinstance(content, str) and content:
                text_messages.append(f"{role}: {content}")

        if not text_messages:
            return "No text messages to summarize."

        conversation_text = "\n".join(text_messages)
        old_count = len(old_messages)

        summary_prompt = (
            "Summarize the following conversation into a concise context "
            "that preserves all key decisions, file changes made, bugs fixed, "
            "and current task state. Be factual and terse.\n\n"
            f"{conversation_text}"
        )

        response = self.model_client.chat(
            messages=[{"role": "user", "content": _sanitize_text(summary_prompt)}],
            system_prompt="You are a conversation summarizer. Output only the summary, no preamble.",
        )

        if response.has_tool_calls:
            logger.warning("Summarizer returned tool_calls, ignoring")

        summary = response.content

        # Replace: summary + recent messages
        self.messages.clear()
        self.messages.append({
            "role": "user",
            "content": "[Earlier context was compacted to save tokens]",
        })
        self.messages.append({
            "role": "assistant",
            "content": summary,
        })
        self.messages.extend(recent_messages)

        if self.token_tracker and response.usage:
            self.token_tracker.record(response.usage, getattr(self.model_client, 'model', 'unknown'))

        logger.info(f"Incremental compact: {old_count} old → summary, {len(recent_messages)} recent preserved")
        return f"Compacted {old_count} old messages → {len(summary)} char summary, {len(recent_messages)} recent messages preserved"

    def compact_with_handoff(self) -> str:
        """Compact the entire conversation into a handoff summary for a new session.

        Unlike compact() which keeps the summary in-place, this produces a
        richer handoff prompt that the next session can use to continue
        seamlessly. The conversation is fully reset after handoff.

        Returns:
            The handoff prompt string (caller should inject into next session).
        """
        text_messages = []
        for msg in self.messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role in ("user", "assistant") and isinstance(content, str) and content:
                text_messages.append(f"{role}: {content}")

        if not text_messages:
            return ""

        conversation_text = "\n".join(text_messages)

        handoff_prompt = (
            "The following is a summary of a previous conversation session. "
            "A new session is starting and needs to continue from where this left off.\n\n"
            "Summarize the conversation preserving:\n"
            "1. All files that were created, edited, or are in context\n"
            "2. All decisions made and their reasoning\n"
            "3. Current task state and what remains to be done\n"
            "4. Any bugs found or issues encountered\n"
            "5. The git state (branch, uncommitted changes)\n\n"
            f"{conversation_text}"
        )

        response = self.model_client.chat(
            messages=[{"role": "user", "content": _sanitize_text(handoff_prompt)}],
            system_prompt="You are a session handoff summarizer. Output a structured handoff document that allows seamless continuation.",
        )

        if response.has_tool_calls:
            logger.warning("Handoff summarizer returned tool_calls, ignoring")

        handoff = response.content

        # Reset conversation completely
        self.messages.clear()
        self.context_files.clear()
        self.web_cache.clear()
        self._structure_injected = False

        if self.token_tracker and response.usage:
            self.token_tracker.record(response.usage, getattr(self.model_client, 'model', 'unknown'))

        logger.info(f"Handoff compact: {len(text_messages)} messages → {len(handoff)} char handoff")
        return handoff

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
