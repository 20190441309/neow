"""Read-only tool calls in one reply run in parallel (plan task 4.4)."""

import threading
import time

from neow.core.agent_loop import AgentLoop, CancelToken, validate_history
from neow.core.approval import ApprovalMode, ApprovalPolicy, ApprovalTier
from neow.core.executor import ToolExecutor
from neow.core.tools_registry import ToolSpec
from tests.test_agent_loop import _call, _conversation

DELAY = 0.3


def _executor(log):
    """Real executor: ``slow_read`` (read-only) and ``slow_write`` (write)."""

    def slow(tag):
        def run(key: str) -> str:
            log.append(("start", key, time.monotonic()))
            time.sleep(DELAY if key != "fast" else 0.01)
            log.append(("end", key, time.monotonic()))
            return f"{tag}:{key}"

        return run

    executor = ToolExecutor()
    for name, read_only, tier in (
        ("slow_read", True, ApprovalTier.READ),
        ("slow_write", False, ApprovalTier.WRITE),
    ):
        executor.register_spec(
            ToolSpec(
                name=name,
                description=name,
                parameters={
                    "type": "object",
                    "properties": {"key": {"type": "string"}},
                    "required": ["key"],
                },
                func=slow(name),
                tier=tier,
                read_only=read_only,
            )
        )
    return executor


def _run(calls, executor):
    conv, _ = _conversation([{"tool_calls": calls}, {"content": "done"}], executor)
    events = []
    started = time.monotonic()
    for chunk in AgentLoop(conv).run("go"):
        if chunk.progress:
            events.append(chunk.progress)
    return conv, events, time.monotonic() - started


def _tool_results(conv):
    return [
        (m["tool_call_id"], m["content"]) for m in conv.messages if m["role"] == "tool"
    ]


def test_parallel_read_only_calls_run_concurrently():
    log = []
    calls = [_call(f"c{i}", "slow_read", key=f"k{i}") for i in range(4)]
    conv, events, elapsed = _run(calls, _executor(log))
    assert elapsed < DELAY * 2.5  # sequential would take 4 × DELAY
    starts = [t for kind, _, t in log if kind == "start"]
    ends = [t for kind, _, t in log if kind == "end"]
    assert max(starts) < min(ends)  # all four were running at once
    kinds = [e["type"] for e in events]
    assert kinds == ["tool_start"] * 4 + ["tool_end"] * 4
    assert all(e["status"] == "ok" for e in events if e["type"] == "tool_end")
    assert validate_history(conv.messages) == []


def test_mixed_calls_run_sequentially():
    log = []
    calls = [
        _call("c1", "slow_read", key="a"),
        _call("c2", "slow_write", key="b"),
        _call("c3", "slow_read", key="c"),
    ]
    executor = _executor(log)
    executor.approval_policy = ApprovalPolicy(mode=ApprovalMode.YOLO)
    conv, events, elapsed = _run(calls, executor)
    assert elapsed >= DELAY * 3
    order = [(kind, key) for kind, key, _ in log]
    assert order == [
        ("start", "a"), ("end", "a"),
        ("start", "b"), ("end", "b"),
        ("start", "c"), ("end", "c"),
    ]
    kinds = [e["type"] for e in events]
    assert kinds == ["tool_start", "tool_end"] * 3


def test_read_only_calls_needing_approval_run_sequentially():
    log = []
    executor = _executor(log)
    executor.approval_policy = ApprovalPolicy(mode=ApprovalMode.ALWAYS_ASK)
    prompts = []

    def approve(name, args, reason):
        prompts.append(threading.current_thread().name)
        return True

    executor.approval_callback = approve
    calls = [_call(f"c{i}", "slow_read", key=f"k{i}") for i in range(2)]
    _, _, elapsed = _run(calls, executor)
    assert elapsed >= DELAY * 2
    assert len(prompts) == 2
    assert all(not name.startswith("neow-tool") for name in prompts)


def test_results_preserve_call_order():
    log = []
    calls = [
        _call("c1", "slow_read", key="slow"),
        _call("c2", "slow_read", key="fast"),
        _call("c3", "missing_tool", key="x"),
        {"id": "c4", "function": {"name": "slow_read", "arguments": "{bad json"}},
    ]
    # Parallel batch (a malformed call does not force sequential execution).
    conv, events, _ = _run([calls[0], calls[1], calls[3]], _executor(log))
    results = _tool_results(conv)
    assert [r[0] for r in results] == ["c1", "c2", "c4"]
    assert results[0][1] == "slow_read:slow" and results[1][1] == "slow_read:fast"
    assert results[2][1].startswith("Error:")
    ends = [e["id"] for e in events if e["type"] == "tool_end"]
    assert ends.index("c2") < ends.index("c1")  # events in completion order

    # An unknown tool is not read-only, so this batch runs sequentially.
    conv, _, _ = _run(calls[:3], _executor([]))
    assert [r[0] for r in _tool_results(conv)] == ["c1", "c2", "c3"]


def test_cancel_during_parallel_calls_keeps_history_valid():
    log = []
    executor = _executor(log)
    calls = [
        _call("c1", "slow_read", key="fast"),
        _call("c2", "slow_read", key="slow"),
    ]
    conv, _ = _conversation([{"tool_calls": calls}, {"content": "done"}], executor)
    cancel = CancelToken()
    ended = {}
    for chunk in AgentLoop(conv).run("go", cancel=cancel):
        if chunk.progress and chunk.progress.get("type") == "tool_end":
            ended[chunk.progress["id"]] = chunk.progress["status"]
            cancel.cancel()
    assert ended == {"c1": "ok", "c2": "error"}  # no card is left running
    results = dict(_tool_results(conv))
    assert results["c1"] == "slow_read:fast"
    assert results["c2"].startswith("Error: cancelled")
    assert validate_history(conv.messages) == []
