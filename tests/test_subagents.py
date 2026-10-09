"""Sub-agents as the ``task`` tool, and architect mode (plan task 4.3)."""

import threading
import time
from types import SimpleNamespace

import pytest

from neow.cli.main import setup_tools
from neow.core.agent_loop import AgentLoop, CancelToken, validate_history
from neow.core.approval import ApprovalMode, ApprovalPolicy
from neow.core.architect import ArchitectOrchestrator
from neow.core.conversation import ConversationManager
from neow.core.executor import ToolExecutor
from neow.core.sub_agent import SubAgent, run_task
from neow.core.token_tracker import TokenTracker
from neow.models.base import StreamChunk
from tests.test_agent_loop import ScriptedClient, _call

USAGE = {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}


class RecordingClient(ScriptedClient):
    """ScriptedClient that also records the tools and system prompt it saw."""

    def __init__(self, replies, delay=0.0):
        super().__init__(replies)
        self.seen = []
        self.delay = delay
        self.lock = threading.Lock()

    def chat_stream(self, messages, system_prompt=None, tools=None):
        is_sub = "## Sub-agent" in (system_prompt or "")
        if is_sub and self.delay:
            time.sleep(self.delay)
        with self.lock:
            self.seen.append(
                {
                    "sub": is_sub,
                    "system": system_prompt,
                    "tools": [t["function"]["name"] for t in tools or []],
                }
            )
            reply = self._next(messages)
        for piece in [reply.get("content", "")]:
            if piece:
                yield StreamChunk(content_delta=piece)
        if reply.get("tool_calls"):
            yield StreamChunk(tool_call_delta={"tool_calls": reply["tool_calls"]})
        if reply.get("usage"):
            yield StreamChunk(usage=reply["usage"])


def _parent(client, mode=ApprovalMode.WRITE, callback=None, tracker=None):
    executor = ToolExecutor()
    setup_tools(executor)
    executor.approval_policy = ApprovalPolicy(mode=mode)
    executor.approval_callback = callback
    conv = ConversationManager(client, tool_executor=executor, token_tracker=tracker)
    conv.tool_provider = executor.get_tool_definitions
    conv.set_system_prompt("You are Neow.")
    return conv


def _run(conv, cancel_on=None):
    cancel = CancelToken()
    events = []
    for chunk in AgentLoop(conv).run("go", cancel=cancel):
        if chunk.progress:
            events.append(chunk.progress)
            if cancel_on and chunk.progress.get("type") == cancel_on:
                cancel.cancel()
    return events


def _tool_results(conv):
    return {
        m["tool_call_id"]: m["content"] for m in conv.messages if m["role"] == "tool"
    }


def test_explore_subagent_has_only_read_only_tools():
    parent = _parent(RecordingClient([]))
    explore = SubAgent(parent, agent_type="explore", description="find usages")
    registry = explore.conversation.tool_executor.registry
    assert len(registry) and all(spec.read_only for spec in registry)
    assert {"grep", "read_file"} <= set(registry.names())
    assert not {"write_file", "execute_command", "task"} & set(registry.names())

    general = SubAgent(parent, agent_type="general")
    names = set(general.conversation.tool_executor.registry.names())
    assert {"write_file", "execute_command"} <= names and "task" not in names
    assert general.conversation.tool_executor is not parent.tool_executor

    with pytest.raises(ValueError, match="agent_type"):
        SubAgent(parent, agent_type="admin")


def test_subagent_runs_in_fresh_context_and_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    client = RecordingClient(
        [
            {
                "tool_calls": [
                    _call("p1", "task", description="inspect a.py", prompt="Look")
                ]
            },
            {"tool_calls": [_call("s1", "read_file", file_path="a.py")]},
            {"content": "a.py sets x = 1", "usage": USAGE},
            {"content": "Done."},
        ]
    )
    tracker = TokenTracker(SimpleNamespace(token={"prices": {}}))
    parent = _parent(client, tracker=tracker)
    parent.memory = SimpleNamespace(text="\n## Project Memory\nUse tabs.\n")
    events = _run(parent)

    assert _tool_results(parent)["p1"] == "a.py sets x = 1"
    # The parent history holds only the call and the report, not the sub-run.
    assert [m["role"] for m in parent.messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    sub = [s for s in client.seen if s["sub"]]
    assert "Task: inspect a.py" in sub[0]["system"]
    assert "Use tabs." in sub[0]["system"]  # project memory reaches sub-agents
    progress = [e["message"] for e in events if e["type"] == "tool_progress"]
    assert progress == ["1 tool call · read_file a.py"]
    assert "Sub-agents: 110 tokens" in tracker.get_session_summary()


def test_general_subagent_uses_parent_approval(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    asked = []

    def approve(name, args, reason):
        asked.append(
            (name, reason, threading.current_thread() is threading.main_thread())
        )
        return True

    client = RecordingClient(
        [
            {
                "tool_calls": [
                    _call(
                        "p1",
                        "task",
                        description="add notes",
                        prompt="Create notes.txt",
                        agent_type="general",
                    )
                ]
            },
            {
                "tool_calls": [
                    _call("s1", "create_file", file_path="notes.txt", content="hi")
                ]
            },
            {"content": "Created notes.txt"},
            {"content": "Done."},
        ]
    )
    parent = _parent(client, callback=approve)
    _run(parent)

    assert (tmp_path / "notes.txt").read_text() == "hi"
    assert len(asked) == 1
    name, reason, on_main_thread = asked[0]
    assert name == "create_file" and reason.startswith("[子 agent · add notes]")
    assert on_main_thread  # relayed to the loop's thread, not the worker
    assert _tool_results(parent)["p1"] == "Created notes.txt"


def test_general_subagent_denied_write_is_not_applied(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = RecordingClient(
        [
            {
                "tool_calls": [
                    _call(
                        "p1", "task", description="d", prompt="p", agent_type="general"
                    )
                ]
            },
            {
                "tool_calls": [
                    _call("s1", "create_file", file_path="x.txt", content="x")
                ]
            },
            {"content": "Could not create x.txt"},
            {"content": "Done."},
        ]
    )
    parent = _parent(client, callback=lambda *a: False)
    _run(parent)
    assert not (tmp_path / "x.txt").exists()


def test_subagent_cancelled_with_parent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    client = RecordingClient(
        [
            {"tool_calls": [_call("p1", "task", description="d", prompt="p")]},
            {"tool_calls": [_call("s1", "read_file", file_path="a.py")]},
            {"content": "never requested"},
        ]
    )
    parent = _parent(client)
    events = _run(parent, cancel_on="tool_progress")
    time.sleep(0.5)  # let the worker notice the cancel
    assert len(client.seen) == 2  # the sub-agent made no request after cancel
    assert [e["status"] for e in events if e["type"] == "tool_end"] == ["error"]
    assert _tool_results(parent)["p1"].startswith("Error: cancelled")
    assert validate_history(parent.messages) == []


def test_no_nested_task():
    parent = _parent(RecordingClient([]))
    sub = SubAgent(parent, agent_type="general")
    assert "task" not in sub.conversation.tool_executor.registry
    assert "task" not in [
        d["function"]["name"] for d in sub.conversation.tool_provider()
    ]
    assert run_task(sub.conversation, "d", "p").startswith("Error: sub-agents cannot")


def test_explore_tasks_run_in_parallel():
    calls = [
        _call(f"p{i}", "task", description=f"q{i}", prompt=f"question {i}")
        for i in range(3)
    ]
    client = RecordingClient(
        [
            {"tool_calls": calls},
            {"content": "r"},
            {"content": "r"},
            {"content": "r"},
            {"content": "Done."},
        ],
        delay=0.3,
    )
    parent = _parent(client)
    started = time.monotonic()
    _run(parent)
    assert time.monotonic() - started < 0.75  # sequential: >= 0.9 s
    assert set(_tool_results(parent).values()) == {"r"}

    # general tasks may edit files, so they run one at a time
    executor = parent.tool_executor
    assert executor.can_run_concurrently("task", {"description": "d", "prompt": "p"})
    assert not executor.can_run_concurrently(
        "task", {"description": "d", "prompt": "p", "agent_type": "general"}
    )


def test_subagent_approval_yolo_is_explicit():
    parent = _parent(RecordingClient([]), callback=lambda *a: True)
    inherited = SubAgent(parent, agent_type="general")
    assert inherited.conversation.tool_executor.approval_policy is (
        parent.tool_executor.approval_policy
    )
    yolo = SubAgent(parent, agent_type="general", approval="yolo")
    policy = yolo.conversation.tool_executor.approval_policy
    assert policy.mode == ApprovalMode.YOLO


def test_architect_no_parallel_writes():
    plan = (
        '```json\n[{"task": "Read main.py", "files": ["main.py"]},'
        ' {"task": "Fix the import"}]\n```'
    )
    orch = ArchitectOrchestrator(ScriptedClient([{"content": plan}]))
    todos, _ = orch.plan("Fix the bug")
    assert todos == [
        {"id": "1", "content": "Read main.py (files: main.py)", "status": "pending"},
        {"id": "2", "content": "Fix the import", "status": "pending"},
    ]
    prompt = orch.execution_prompt("Fix the bug", todos)
    assert "todo_write" in prompt and "1. Read main.py" in prompt
    # Execution happens in the main conversation; nothing here runs tools.
    assert not hasattr(orch, "_execute_sub_tasks")

    direct = ArchitectOrchestrator(ScriptedClient([{"content": "Just rename it."}]))
    assert direct.plan("tiny") == ([], "Just rename it.")


async def test_tui_task_card_shows_subagent_progress():
    from neow.tui.bridge.events import ToolFinished, ToolProgress, ToolStarted
    from neow.tui.screens.chat import ChatScreen
    from neow.tui.widgets.cards import ToolCard
    from tests.tui.conftest import FakeConversation, _chat_app

    app = _chat_app(FakeConversation(script=[]))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ChatScreen)
        args = {"description": "find callers", "prompt": "p"}
        screen.handle_event(ToolStarted(name="task", args=args, call_id="t1"))
        screen.handle_event(
            ToolProgress(name="task", message="2 tool calls · grep foo", call_id="t1")
        )
        await pilot.pause()
        card = screen.query_one(ToolCard)
        assert "explore · find callers" in card.title_text()
        assert "2 tool calls · grep foo" in card.title_text()
        screen.handle_event(
            ToolFinished(
                name="task", result="report", is_error=False, denied=False, call_id="t1"
            )
        )
        await pilot.pause()
        assert "grep foo" not in card.title_text()  # replaced by the duration
