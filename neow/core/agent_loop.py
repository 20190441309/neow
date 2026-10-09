"""The agent loop: request → collect → run tools → repeat.

One implementation serves both the streaming and the blocking API of
:class:`~neow.core.conversation.ConversationManager`.  Every exit path
(normal, exception, cancellation, ``GeneratorExit``) leaves the message
history valid: each assistant ``tool_call`` has a matching tool result.
"""

import json
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, List, Optional, Tuple

from neow.core.cancellation import CancelToken, cancellation_scope
from neow.core.executor import ToolDenied
from neow.models.base import ModelResponse, StreamChunk, normalize_finish_reason
from neow.utils import sanitize_text
from neow.utils.logger import logger

DEFAULT_MAX_TURNS = 50
DEFAULT_MAX_TOOL_OUTPUT_CHARS = 30000
CANCELLED_RESULT = "Error: cancelled before execution"
MAX_TURNS_RESULT = "Error: not executed (tool call limit reached)"
TRUNCATED_RESULT = (
    "Error: not executed: your reply hit the output token limit "
    "(max_output_tokens) and the tool arguments were cut off. "
    "Split the change into smaller edits."
)

# Tools whose successful run should refresh a file held in conversation context.
FILE_MUTATING_TOOLS = {"write_file", "edit_file", "create_file", "delete_file"}


def validate_history(messages: List[Dict[str, Any]]) -> List[str]:
    """Describe tool-call/result mismatches (empty list = valid)."""

    problems: List[str] = []
    open_calls: List[str] = []
    seen_calls = set()

    def close_open() -> None:
        problems.extend(f"tool call '{cid}' has no result" for cid in open_calls)
        open_calls.clear()

    for message in messages:
        role = message.get("role")
        if role == "tool":
            call_id = message.get("tool_call_id")
            if call_id in open_calls:
                open_calls.remove(call_id)
            elif call_id not in seen_calls:
                problems.append(f"tool result '{call_id}' has no matching call")
            continue
        close_open()
        for call in message.get("tool_calls") or []:
            open_calls.append(call["id"])
            seen_calls.add(call["id"])
    close_open()
    return problems


def repair_history(messages: List[Dict[str, Any]], result: str) -> int:
    """Insert *result* for every tool call lacking one; returns how many."""

    repaired = 0
    index = 0
    while index < len(messages):
        message = messages[index]
        calls = (
            message.get("tool_calls") if message.get("role") == "assistant" else None
        )
        if not calls:
            index += 1
            continue
        # Results for this assistant message follow it contiguously.
        end = index + 1
        answered = set()
        while end < len(messages) and messages[end].get("role") == "tool":
            answered.add(messages[end].get("tool_call_id"))
            end += 1
        for call in calls:
            if call["id"] not in answered:
                messages.insert(end, _tool_message(call["id"], result))
                end += 1
                repaired += 1
        index = end
    return repaired


def _tool_message(call_id: str, result: str) -> Dict[str, Any]:
    # DeepSeek requires the 'type' field on tool messages.
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": sanitize_text(str(result)),
        "type": "tool_result",
    }


def truncate_tool_output(
    text: str, limit: int = DEFAULT_MAX_TOOL_OUTPUT_CHARS
) -> str:
    """Keep the head (60%) and tail (40%) of an over-long tool result."""

    if len(text) <= limit:
        return text
    head = int(limit * 0.6)
    tail = limit - head
    dropped = len(text) - head - tail
    return (
        f"{text[:head]}\n… [truncated {dropped} chars; re-run with a narrower "
        f"scope, e.g. read_file offset/limit or a more specific command] …\n"
        f"{text[-tail:]}"
    )


def parse_tool_arguments(raw: Any) -> Tuple[Any, Optional[str]]:
    """Decode a tool call's JSON arguments.

    Returns ``(arguments, None)`` or ``(None, error result for the model)``.
    An empty string means "no arguments" (some providers send that).
    """

    if isinstance(raw, dict):
        return raw, None
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return {}, None
    try:
        arguments = json.loads(raw)
    except (TypeError, ValueError) as exc:
        detail = getattr(exc, "msg", str(exc))
        position = getattr(exc, "pos", None)
        where = f" at character {position}" if position is not None else ""
        return None, (
            f"Error: invalid JSON in tool arguments ({detail}{where}). "
            "Re-issue the call with valid JSON arguments."
        )
    if not isinstance(arguments, dict):
        return None, (
            "Error: tool arguments must be a JSON object, got "
            f"{type(arguments).__name__}. Re-issue the call with an object."
        )
    return arguments, None


def _notice(message: str, level: str = "warn") -> StreamChunk:
    logger.warning(message)
    return StreamChunk(progress={"type": "notice", "level": level, "message": message})


def _chunks_from_response(response: ModelResponse) -> Iterable[StreamChunk]:
    """Present a blocking ``chat()`` reply as a one-chunk stream."""

    tool_calls = list(response.tool_calls) if response.has_tool_calls else None
    yield StreamChunk(
        content_delta=response.content or "",
        tool_call_delta={"tool_calls": tool_calls} if tool_calls else None,
        usage=response.usage or None,
        finish_reason=getattr(response, "finish_reason", None),
    )


class AgentLoop:
    """Runs one user turn against a :class:`ConversationManager`."""

    def __init__(self, conversation: Any, *, max_turns: int = DEFAULT_MAX_TURNS):
        self.conversation = conversation
        self.max_turns = max_turns
        self.result = ModelResponse(content="")
        self._unsaved_content = ""

    def run(
        self,
        user_input: str,
        *,
        stream: bool = True,
        cancel: Optional[CancelToken] = None,
    ) -> Generator[StreamChunk, None, None]:
        """Yield model chunks and progress events; final reply in ``result``."""

        conv = self.conversation
        cancel = cancel or CancelToken()
        conv.messages.append(
            {"role": "user", "content": conv._build_vision_content(user_input)}
        )
        reason = CANCELLED_RESULT
        try:
            for request_number in range(1, self.max_turns + 1):
                response = yield from self._request(user_input, stream)
                if cancel.cancelled():
                    break
                truncated = response.finish_reason == "length"
                if not response.tool_calls or conv.tool_executor is None:
                    self._append_assistant(response.content)
                    if truncated:
                        yield _notice(
                            "回复达到输出上限（max_output_tokens）被截断，"
                            "可让模型继续，或在配置中调高该值"
                        )
                    break
                self._append_assistant(response.content, response.tool_calls)
                if truncated:
                    # The last call's arguments are cut off; run none of them
                    # and let the model retry with smaller edits.
                    for call in response.tool_calls:
                        conv.add_tool_result(call["id"], TRUNCATED_RESULT)
                    yield _notice(
                        "输出达到上限（max_output_tokens），已让模型拆分后重试"
                    )
                    continue
                if request_number == self.max_turns:
                    reason = MAX_TURNS_RESULT
                    yield _notice(
                        f"本轮已请求模型 {self.max_turns} 次，达到上限"
                        "（agent.max_turns），已停止"
                    )
                    break
                yield from self._run_tools(response.tool_calls, cancel)
                if cancel.cancelled():
                    break
        finally:
            if self._unsaved_content:
                self._append_assistant(self._unsaved_content)
            repaired = repair_history(conv.messages, reason)
            if repaired:
                logger.info(f"Filled {repaired} unanswered tool call(s): {reason}")

    # -- one model request ------------------------------------------------

    def _request(
        self, user_input: str, stream: bool
    ) -> Generator[StreamChunk, None, ModelResponse]:
        conv = self.conversation
        messages = [
            {k: sanitize_text(v) if isinstance(v, str) else v for k, v in msg.items()}
            for msg in conv.messages
        ]
        kwargs = dict(
            messages=messages,
            system_prompt=conv._get_effective_system_prompt(user_input),
            tools=conv._tool_definitions(),
        )
        chunks = (
            conv.model_client.chat_stream(**kwargs)
            if stream
            else _chunks_from_response(conv.model_client.chat(**kwargs))
        )

        tool_calls: List[Dict[str, Any]] = []
        usage: Dict[str, int] = {}
        finish_reason: Optional[str] = None
        reasoning_active = False
        self._unsaved_content = ""
        for chunk in chunks:
            if chunk.reasoning_delta and not reasoning_active:
                reasoning_active = True
                yield StreamChunk(progress={"type": "reasoning_start"})
            if chunk.content_delta and reasoning_active:
                reasoning_active = False
                yield StreamChunk(progress={"type": "reasoning_end"})
            if chunk.content_delta:
                self._unsaved_content += chunk.content_delta
            if chunk.tool_call_delta:
                tool_calls = chunk.tool_call_delta.get("tool_calls") or []
            if chunk.usage:
                usage = chunk.usage
            if chunk.finish_reason:
                finish_reason = normalize_finish_reason(chunk.finish_reason)
            yield chunk
        if reasoning_active:
            yield StreamChunk(progress={"type": "reasoning_end"})

        if conv.token_tracker and usage:
            conv.token_tracker.record(
                usage, getattr(conv.model_client, "model", "unknown")
            )
        response = ModelResponse(
            content=self._unsaved_content,
            tool_calls=tool_calls,
            usage=usage,
            finish_reason=finish_reason,
        )
        self.result = ModelResponse(content=response.content, usage=usage)
        return response

    # -- tools ------------------------------------------------------------

    def _run_tools(
        self, tool_calls: List[Dict[str, Any]], cancel: CancelToken
    ) -> Generator[StreamChunk, None, None]:
        conv = self.conversation
        for call in tool_calls:
            if cancel.cancelled():
                return
            name = call["function"]["name"]
            call_id = call["id"]
            arguments, parse_error = parse_tool_arguments(
                call["function"].get("arguments")
            )
            yield StreamChunk(
                progress={
                    "type": "tool_start",
                    "name": name,
                    "args": arguments if isinstance(arguments, dict) else {},
                    "id": call_id,
                }
            )
            status = "ok"
            if parse_error:
                result, status = parse_error, "error"
            else:
                try:
                    with cancellation_scope(cancel):
                        result = str(conv.tool_executor.execute(name, arguments))
                except ToolDenied as e:
                    result, status = f"Error: {e}", "denied"
                except Exception as e:
                    result, status = f"Error: {e}", "error"
                if status == "ok" and result.startswith("Error:"):
                    status = "error"
            yield StreamChunk(
                progress={
                    "type": "tool_end",
                    "name": name,
                    "result": result[:500],
                    "id": call_id,
                    "status": status,
                }
            )
            if status == "ok":
                self._refresh_context(name, arguments)
            limit = getattr(
                conv, "max_tool_output_chars", DEFAULT_MAX_TOOL_OUTPUT_CHARS
            )
            conv.add_tool_result(call_id, truncate_tool_output(result, limit))

    def _refresh_context(self, tool_name: str, arguments: Dict[str, Any]) -> None:
        conv = self.conversation
        if tool_name not in FILE_MUTATING_TOOLS:
            return
        edited_path = arguments.get("file_path", "")
        if not edited_path:
            return
        abs_path = str(Path(edited_path).resolve())
        if abs_path in conv.context_files:
            if tool_name == "delete_file":
                del conv.context_files[abs_path]
            else:
                conv.refresh_context_file(abs_path)

    # -- history ----------------------------------------------------------

    def _append_assistant(
        self, content: str, tool_calls: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        message: Dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            message["tool_calls"] = [
                {"id": tc["id"], "type": "function", "function": tc["function"]}
                for tc in tool_calls
            ]
        # DeepSeek thinking mode: reasoning_content must be passed back.
        reasoning = getattr(
            self.conversation.model_client, "_last_reasoning_content", None
        )
        if isinstance(reasoning, str) and reasoning:
            message["reasoning_content"] = reasoning
        self.conversation.messages.append(message)
        self._unsaved_content = ""


__all__ = [
    "AgentLoop",
    "CancelToken",
    "validate_history",
    "repair_history",
    "DEFAULT_MAX_TURNS",
]
