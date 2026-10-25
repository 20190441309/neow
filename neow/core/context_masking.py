"""Observation masking for older bulky tool outputs in conversation history."""

from __future__ import annotations

from typing import Any, Dict, List

DEFAULT_KEEP_RECENT_TURNS = 4
DEFAULT_MASK_MIN_CHARS = 1500
PREVIEW_HEAD_CHARS = 240
PREVIEW_TAIL_CHARS = 120


def mask_old_observations(
    messages: List[Dict[str, Any]],
    keep_recent_turns: int = DEFAULT_KEEP_RECENT_TURNS,
    min_chars: int = DEFAULT_MASK_MIN_CHARS,
) -> List[Dict[str, Any]]:
    """Return a shallow-copied message list with old bulky tool outputs masked.

    Preserves the last ``keep_recent_turns`` assistant tool-call turns in full
    detail so the model has complete context for its immediate work, while
    collapsing older ``role == "tool"`` outputs longer than ``min_chars`` into
    a compact preview header + footer. The original ``messages`` list is not
    mutated.
    """
    if not messages:
        return []

    # Identify indices of assistant messages that made tool calls
    assistant_turn_indices = [
        idx
        for idx, msg in enumerate(messages)
        if msg.get("role") == "assistant" and msg.get("tool_calls")
    ]

    if len(assistant_turn_indices) <= keep_recent_turns:
        return list(messages)

    cutoff_idx = assistant_turn_indices[-keep_recent_turns]
    masked: List[Dict[str, Any]] = []

    for idx, msg in enumerate(messages):
        if idx < cutoff_idx and msg.get("role") == "tool":
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > min_chars:
                head = content[:PREVIEW_HEAD_CHARS].replace("\n", " ").strip()
                tail = content[-PREVIEW_TAIL_CHARS:].replace("\n", " ").strip()
                compact = (
                    f"[已折叠历史工具输出 ({len(content)} 字符) · "
                    f"头部预览: {head} … 尾部预览: {tail}]"
                )
                new_msg = dict(msg)
                new_msg["content"] = compact
                masked.append(new_msg)
                continue
        masked.append(msg)

    return masked
