"""Autonomous goal-driven execution mode (/goal)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

GOAL_COMPLETION_MARKER = "<GOAL_ACHIEVED>"
DEFAULT_MAX_GOAL_ROUNDS = 10


@dataclass
class GoalState:
    """Tracks an active /goal autonomous execution session."""

    goal: str
    active: bool = True
    current_round: int = 1
    max_rounds: int = DEFAULT_MAX_GOAL_ROUNDS


def build_goal_initial_prompt(goal: str) -> str:
    """Wrap a user goal in an autonomous multi-step execution directive."""
    goal = goal.strip()
    return (
        f"[AUTONOMOUS GOAL MODE]\n"
        f"目标 (Goal): {goal}\n\n"
        "请进入自主目标达成模式，严格遵循以下执行准则直到目标 100% 完成：\n"
        "1. **拆解规划**：首先使用 `todo_write` 工具将目标拆解为清晰、可验证的子任务列表，"
        "将当前正在执行的步骤标记为 `in_progress`，其余为 `pending`。\n"
        "2. **彻底执行**：逐步完成每个子任务，禁止半途而废或仅给出伪代码建议。"
        "每次完成一个子任务后立即用 `todo_write` 将其更新为 `completed`。\n"
        "3. **严格验证**：修改代码后必须运行相关测试或检查命令（`execute_command`）"
        "验证改动是否真正生效且无回归错误。\n"
        f"4. **完成标记**：仅当所有 `todo_write` 子任务均已标记为 `completed` 且目标已通过验证时，"
        f"在最终回复末尾输出标记 `{GOAL_COMPLETION_MARKER}`。"
    )


def is_goal_achieved(
    last_reply: str, todos: Optional[List[Dict[str, str]]] = None
) -> bool:
    """Return True if the goal has been achieved based on reply marker and todos."""
    reply_text = (last_reply or "").strip()
    todos_list = list(todos or [])
    has_incomplete_todos = any(
        t.get("status") in ("pending", "in_progress") for t in todos_list
    )
    if has_incomplete_todos:
        return False
    if GOAL_COMPLETION_MARKER in reply_text or "[GOAL_ACHIEVED]" in reply_text:
        return True
    if todos_list and all(t.get("status") == "completed" for t in todos_list):
        return True
    return False


def build_goal_continuation_prompt(
    state: GoalState, todos: Optional[List[Dict[str, str]]] = None
) -> str:
    """Build the prompt for the next autonomous round when the goal is not yet met."""
    todos_list = list(todos or [])
    remaining = [
        t["content"]
        for t in todos_list
        if t.get("status") in ("pending", "in_progress") and t.get("content")
    ]
    if remaining:
        todo_block = "当前尚未完成的子任务：\n" + "\n".join(
            f"- {item}" for item in remaining
        )
    else:
        todo_block = "当前尚未检测到完成标记或完整的验证结果。"

    return (
        f"[AUTONOMOUS GOAL CONTINUATION · "
        f"第 {state.current_round}/{state.max_rounds} 轮]\n"
        f"目标 (Goal): {state.goal}\n"
        f"{todo_block}\n\n"
        "请继续推进并完成剩余工作，运行测试或验证命令确认无误，更新 `todo_write` 状态。"
        f"当且仅当所有子任务均已完成并通过验证后，在回复末尾输出 `{GOAL_COMPLETION_MARKER}`。"
    )


__all__ = [
    "DEFAULT_MAX_GOAL_ROUNDS",
    "GOAL_COMPLETION_MARKER",
    "GoalState",
    "build_goal_continuation_prompt",
    "build_goal_initial_prompt",
    "is_goal_achieved",
]
