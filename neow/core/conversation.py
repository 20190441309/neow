"""Conversation manager for Neow CLI."""

import hashlib
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

from neow.core.agent_loop import (
    DEFAULT_MAX_TOOL_OUTPUT_CHARS,
    DEFAULT_MAX_TURNS,
    AgentLoop,
    CancelToken,
)
from neow.models.base import (
    DEFAULT_CONTEXT_WINDOW,
    BaseModelClient,
    ModelResponse,
    StreamChunk,
)
from neow.utils import sanitize_text as _sanitize_text
from neow.utils.logger import logger


AUTO_COMPACT_THRESHOLD = 0.8


def _estimate_tokens(messages: List[Dict[str, Any]]) -> int:
    """Rough token count (~4 characters per token)."""
    chars = 0
    for message in messages:
        content = message.get("content")
        chars += len(content) if isinstance(content, str) else len(str(content or ""))
        for call in message.get("tool_calls") or []:
            chars += len(str(call.get("function", {}).get("arguments", "")))
    return chars // 4


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
        registry = getattr(self.tool_executor, "registry", None)
        if registry is not None and "todo_write" in registry:
            registry.bind("todo_write", self.write_todos)
        if registry is not None and "task" in registry:
            from functools import partial

            from neow.core.sub_agent import run_task

            registry.bind("task", partial(run_task, self))
        # "subagent" for sub-agent conversations (token accounting, no nesting).
        self.usage_source = "main"
        self.subagent_approval = "inherit"  # or "yolo" (agent.subagent_approval)
        self.subagent_max_turns = 25
        self.messages: List[Dict[str, Any]] = []
        self.system_prompt: str = ""
        self.tools: List[Dict[str, Any]] = []
        # When set, called on every request instead of using ``self.tools``.
        self.tool_provider: Optional[Callable[[], List[Dict[str, Any]]]] = None
        self.context_files: Dict[str, str] = {}  # abs_path -> content
        self.context_manager = context_manager
        self.token_tracker = token_tracker
        self._structure_injected = False
        self._structure_text: Optional[str] = None
        # Instructions from AGENTS.md / NEOW.md (neow.core.memory.Memory).
        self.memory: Optional[Any] = None
        # MCP connections (neow.core.mcp_client.MCPManager), for /mcp.
        self.mcp: Optional[Any] = None
        # User hooks (neow.core.hooks.HookRunner), run by the agent loop.
        self.hooks: Optional[Any] = None
        self.web_cache: Dict[str, Any] = {}  # url -> WebContent
        # Task list kept by the todo_write tool (neow.core.todos).
        self.todos: List[Dict[str, str]] = []
        self.pending_lint_feedback: Optional[str] = None
        self._pending_images: List[Dict[str, Any]] = []  # queued images for next message
        self.max_turns = DEFAULT_MAX_TURNS  # model requests allowed per user turn
        # Provider-reported size of the context after the last reply, and the
        # message it was measured at (see context_usage()).
        self._usage_tokens = 0
        self._usage_anchor: Optional[Dict[str, Any]] = None
        self._usage_length = 0
        # Longest tool result kept in history (head + tail beyond this).
        self.max_tool_output_chars = DEFAULT_MAX_TOOL_OUTPUT_CHARS

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

    def _tool_definitions(self) -> Optional[List[Dict[str, Any]]]:
        """Tools to offer the model for the next request (None if none)."""
        tools = self.tool_provider() if self.tool_provider else self.tools
        return tools or None

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
    def get_response(
        self, user_input: str, *, cancel: Optional[CancelToken] = None
    ) -> ModelResponse:
        """Get AI response for user input (blocking).

        Runs the full tool loop; see :class:`~neow.core.agent_loop.AgentLoop`.

        Args:
            user_input: User input text.
            cancel: Optional token to stop the turn early.

        Returns:
            ModelResponse with the final reply text and last usage.
        """
        loop = AgentLoop(self, max_turns=self.max_turns)
        for _ in loop.run(user_input, stream=False, cancel=cancel):
            pass
        logger.info(f"Response generated ({loop.result.usage.get('total_tokens', 0)} tokens)")
        return loop.result

    def get_response_stream(
        self, user_input: str, *, cancel: Optional[CancelToken] = None
    ) -> Generator[StreamChunk, None, None]:
        """Get streaming AI response for user input.

        Args:
            user_input: User input text.
            cancel: Optional token to stop the turn early.

        Yields:
            StreamChunk objects (model output and progress events).
        """
        loop = AgentLoop(self, max_turns=self.max_turns)
        yield from loop.run(user_input, stream=True, cancel=cancel)

    # -- context usage ----------------------------------------------------

    def record_context_usage(self, usage: Dict[str, int]) -> None:
        """Remember the provider's token count for the history as it is now."""
        prompt = usage.get("prompt_tokens") or 0
        total = prompt + (usage.get("completion_tokens") or 0)
        if total and self.messages:
            self._usage_tokens = total
            self._usage_anchor = self.messages[-1]
            self._usage_length = len(self.messages)

    def context_usage(self) -> Tuple[int, int, float]:
        """``(tokens, context_window, percent)`` for the next request.

        Uses the last provider-reported count plus an estimate for messages
        added since.  If the history was rewritten (clear, compaction, load)
        the anchor message is gone and everything is estimated (~4 chars per
        token).
        """
        window = getattr(self.model_client, "context_window", None)
        if not isinstance(window, int) or window < 1:
            window = DEFAULT_CONTEXT_WINDOW
        length = self._usage_length
        valid = (
            self._usage_anchor is not None
            and len(self.messages) >= length
            and self.messages[length - 1] is self._usage_anchor
        )
        if valid:
            tokens = self._usage_tokens + _estimate_tokens(self.messages[length:])
        else:
            tokens = _estimate_tokens(self.messages) + len(self.system_prompt) // 4
        return tokens, window, tokens / window * 100

    def should_auto_compact(self, threshold: float = AUTO_COMPACT_THRESHOLD) -> bool:
        """True when the context is past *threshold* of the model's window."""
        _, _, percent = self.context_usage()
        return percent >= threshold * 100 and len(self.messages) > 4

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

    def write_todos(self, todos: Any) -> str:
        """Implementation of the ``todo_write`` tool: replace the task list."""
        from neow.core.todos import format_todos, todo_summary, validate_todos

        self.todos = validate_todos(todos)
        return f"Todos updated ({todo_summary(self.todos)}):\n" + format_todos(
            self.todos
        )

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.messages.clear()
        self.todos = []
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

    # -- context -----------------------------------------------------------
    #
    # The system prompt stays identical for the whole session so providers
    # can cache it.  Context that changes (files added with /add, fetched web
    # pages, files matching the question) travels in a user message tagged
    # ``neow_context`` placed before the user's own message, and is only sent
    # again when its content changes.  Hashes live on those messages, so
    # /clear, compaction and session restore naturally trigger a resend.

    def _project_structure(self) -> str:
        """Project structure summary, computed once per session."""
        if not self.context_manager:
            return ""
        if not self._structure_injected or self._structure_text is None:
            from neow.core.prompts import format_project_context

            structure = self.context_manager.get_project_structure(max_depth=2)
            self._structure_text = format_project_context(structure, [])
            self._structure_injected = True
        return self._structure_text

    def _context_items(self, user_input: str) -> List[Tuple[str, str]]:
        """``(key, section text)`` for every piece of dynamic context."""
        items: List[Tuple[str, str]] = []
        for path, content in self.context_files.items():
            items.append((f"file:{path}", f"### File: {path}\n```\n{content}\n```"))
        for url, content in self.web_cache.items():
            parts = [f"### Web page: {content.title} ({url})", content.text]
            for lang, code in content.code_blocks:
                parts.append(f"```{lang}\n{code}\n```")
            items.append((f"web:{url}", "\n".join(parts)))
        if self.context_manager and user_input:
            for found in self.context_manager.get_relevant_files(user_input) or []:
                path = found.get("path", "")
                items.append(
                    (
                        f"relevant:{path}",
                        f"### Possibly relevant: {path}\n```\n"
                        f"{found.get('content', '')}\n```",
                    )
                )
        return items

    def build_context_message(self, user_input: str = "") -> Optional[Dict[str, Any]]:
        """User message carrying context the model has not seen yet, or None."""
        sent: Dict[str, str] = {}
        for message in self.messages:
            sent.update(message.get("neow_context") or {})
        fresh: Dict[str, str] = {}
        sections: List[str] = []
        for key, text in self._context_items(user_input):
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
            if sent.get(key) == digest or key in fresh:
                continue
            fresh[key] = digest
            sections.append(text)
        if not sections:
            return None
        body = "\n\n".join(sections)
        return {
            "role": "user",
            "content": (
                "<context>\nCurrent content of files and pages the user shared "
                "(newer versions replace earlier ones):\n\n"
                f"{body}\n</context>"
            ),
            "neow_context": fresh,
        }

    def _get_effective_system_prompt(self, user_input: str = "") -> Optional[str]:
        """System prompt sent with every request: stable for the session.

        Args:
            user_input: Unused; kept for callers of the old signature.

        Returns:
            Base prompt plus the project structure summary, or None if empty.
        """
        memory = getattr(self.memory, "text", "") or ""
        prompt = self.system_prompt + memory + self._project_structure()
        return prompt or None
