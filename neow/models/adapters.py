"""Convert neow's internal (OpenAI-style) messages to each provider's format.

neow stores history in OpenAI Chat format: ``role: user|assistant|tool``,
assistant ``tool_calls`` and ``tool_call_id`` on results.  User content is a
string or a list of blocks (``text`` and Anthropic-style ``image`` blocks
queued by ``/image``).  Clients call these adapters at the request
boundary; inputs are never mutated.
"""

import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

from neow.utils.logger import logger

OPENAI_MESSAGE_KEYS = {
    "system": {"role", "content"},
    "user": {"role", "content", "name"},
    "assistant": {"role", "content", "tool_calls", "name"},
    "tool": {"role", "content", "tool_call_id"},
}

_EMPTY_RESULT = "(no output)"


# -- OpenAI / OpenAI-compatible ---------------------------------------------


def to_openai(
    messages: List[Dict[str, Any]], extra_keys: Iterable[str] = ()
) -> List[Dict[str, Any]]:
    """OpenAI Chat Completions messages.

    Drops non-standard keys (except *extra_keys*, e.g. DeepSeek's
    ``reasoning_content``) and converts image blocks to ``image_url`` parts.
    """

    keep_extra = set(extra_keys)
    converted = []
    for message in messages:
        allowed = OPENAI_MESSAGE_KEYS.get(message.get("role"), set(message))
        out = {k: v for k, v in message.items() if k in allowed or k in keep_extra}
        if isinstance(out.get("content"), list):
            out["content"] = [_openai_part(part) for part in out["content"]]
        converted.append(out)
    return converted


def _openai_part(part: Dict[str, Any]) -> Dict[str, Any]:
    if part.get("type") != "image":
        return part
    source = part.get("source", {})
    url = (
        f"data:{source.get('media_type', 'image/png')};base64,{source.get('data', '')}"
    )
    return {"type": "image_url", "image_url": {"url": url}}


# -- Anthropic Messages API ---------------------------------------------------


def anthropic_tools(tools: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Tool definitions as ``{name, description, input_schema}``."""

    converted = []
    for tool in tools or []:
        if "input_schema" in tool:
            converted.append(tool)
            continue
        function = tool.get("function", tool)
        converted.append(
            {
                "name": function["name"],
                "description": function.get("description", ""),
                "input_schema": function.get("parameters")
                or {"type": "object", "properties": {}},
            }
        )
    return converted


def to_anthropic(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Anthropic ``messages`` and ``tools`` for the same conversation.

    - assistant ``tool_calls`` become ``tool_use`` blocks
    - consecutive tool results become ``tool_result`` blocks at the start of
      one user message, as the API requires
    - consecutive same-role messages are merged; empty text is dropped
    """

    merged: List[Dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "assistant":
            blocks = _assistant_blocks(message)
            api_role = "assistant"
        elif role == "tool":
            blocks = [_tool_result_block(message)]
            api_role = "user"
        elif role == "user":
            blocks = _content_blocks(message.get("content"))
            api_role = "user"
        else:
            continue  # system prompts travel in the `system` parameter
        if not blocks:
            continue
        if merged and merged[-1]["role"] == api_role:
            merged[-1]["content"] = _merge_blocks(merged[-1]["content"], blocks)
        else:
            merged.append({"role": api_role, "content": blocks})
    return merged, anthropic_tools(tools)


def _content_blocks(content: Any) -> List[Dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    blocks = []
    for block in content or []:
        if block.get("type") == "text" and not block.get("text"):
            continue
        blocks.append(dict(block))
    return blocks


def _assistant_blocks(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    blocks = _content_blocks(message.get("content"))
    for call in message.get("tool_calls") or []:
        function = call.get("function", {})
        blocks.append(
            {
                "type": "tool_use",
                "id": call["id"],
                "name": function.get("name", ""),
                "input": _parse_arguments(call["id"], function.get("arguments")),
            }
        )
    return blocks


def _parse_arguments(call_id: str, arguments: Any) -> Dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    try:
        parsed = json.loads(arguments or "{}")
    except (TypeError, ValueError):
        logger.warning(f"Tool call {call_id}: arguments are not valid JSON")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _tool_result_block(message: Dict[str, Any]) -> Dict[str, Any]:
    content = str(message.get("content") or "") or _EMPTY_RESULT
    block: Dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": message.get("tool_call_id", ""),
        "content": content,
    }
    if content.startswith("Error:"):
        block["is_error"] = True
    return block


def _merge_blocks(
    existing: List[Dict[str, Any]], new: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    # tool_result blocks must lead a user message.
    combined = existing + new
    results = [b for b in combined if b.get("type") == "tool_result"]
    others = [b for b in combined if b.get("type") != "tool_result"]
    return results + others


__all__ = ["to_openai", "to_anthropic", "anthropic_tools"]
