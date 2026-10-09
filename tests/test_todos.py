"""Task list tool ``todo_write`` (plan task 4.2)."""

import pytest

from neow.core.agent_loop import AgentLoop
from neow.core.approval import ApprovalMode, ApprovalPolicy
from neow.core.executor import ToolExecutor
from neow.core.session import SessionManager
from neow.core.todos import TodoError, format_todos, validate_todos
from neow.tools.builtin import builtin_specs
from neow.tui.screens.chat import ChatScreen
from neow.tui.widgets.cards import TodoCard, ToolCard
from tests.test_agent_loop import _call, _conversation
from tests.tui.conftest import Chunk, FakeConversation, _chat_app

PLAN = [
    {"id": "1", "content": "Read the parser", "status": "completed"},
    {"id": "2", "content": "Fix the bug", "status": "in_progress"},
    {"id": "3", "content": "Run the tests", "status": "pending"},
]


def test_todo_write_validates_single_in_progress():
    with pytest.raises(TodoError, match="only one"):
        validate_todos(
            [
                {"content": "a", "status": "in_progress"},
                {"content": "b", "status": "in_progress"},
            ]
        )
    with pytest.raises(TodoError, match="status"):
        validate_todos([{"content": "a", "status": "done"}])
    with pytest.raises(TodoError, match="no content"):
        validate_todos([{"content": " ", "status": "pending"}])
    with pytest.raises(TodoError, match="duplicate"):
        validate_todos(
            [{"id": "x", "content": "a", "status": "pending"}] * 2
        )
    # ids default to the position; a JSON string is accepted too
    items = validate_todos('[{"content": "a", "status": "pending"}]')
    assert items == [{"id": "1", "content": "a", "status": "pending"}]
    assert format_todos(PLAN) == "☑ Read the parser\n▶ Fix the bug\n☐ Run the tests"


def _run_todo_call(todos, executor=None):
    executor = executor or ToolExecutor()
    conv, _ = _conversation(
        [{"tool_calls": [_call("t1", "todo_write", todos=todos)]}, {"content": "ok"}],
        executor,
    )
    events = [c.progress for c in AgentLoop(conv).run("go") if c.progress]
    return conv, events


def test_todo_write_updates_conversation_without_approval():
    executor = ToolExecutor()
    executor.approval_policy = ApprovalPolicy(mode=ApprovalMode.ALWAYS_ASK)
    executor.approval_callback = lambda *a: pytest.fail("todo_write asked")
    conv, events = _run_todo_call(PLAN, executor)
    assert conv.todos == PLAN
    result = next(m for m in conv.messages if m["role"] == "tool")["content"]
    assert result.startswith("Todos updated (1/3 done)") and "▶ Fix the bug" in result

    bad, events = _run_todo_call([{"content": "x", "status": "nope"}])
    assert bad.todos == []
    assert events[-1]["status"] == "error"


def test_todo_spec_is_bookkeeping():
    spec = next(s for s in builtin_specs() if s.name == "todo_write")
    assert spec.tier.value == "none" and not spec.read_only


def test_todos_persist_in_session(tmp_path):
    manager = SessionManager(tmp_path)
    conv, _ = _conversation([])
    conv.write_todos(PLAN)
    name = manager.save(conv, "plan")
    restored, _ = _conversation([])
    assert manager.restore(name, restored)
    assert restored.todos == PLAN
    restored.clear_history()
    assert restored.todos == []


class TodoConversation(FakeConversation):
    """Replays two todo_write calls, updating ``todos`` like the real loop."""

    def get_response_stream(self, user_input, cancel=None):
        for step, todos in enumerate((PLAN[:2], PLAN), 1):
            call = {"type": "tool_start", "name": "todo_write", "id": f"t{step}"}
            yield Chunk(progress=dict(call, args={"todos": todos}))
            self.todos = [dict(t) for t in todos]
            yield Chunk(progress=dict(call, type="tool_end", result="ok", status="ok"))
        yield Chunk(content_delta="done")


async def test_tui_todo_card_updates_in_place():
    app = _chat_app(TodoConversation(todos=[]))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ChatScreen)
        screen.submit_prompt("plan it")
        for _ in range(20):
            await pilot.pause()
            if not screen._busy:
                break
        cards = list(screen.query(TodoCard))
        assert len(cards) == 1  # second update reused the card
        assert cards[0].todos == PLAN
        assert "1/3 done" in cards[0].title_text()
        assert "▶ Fix the bug" in cards[0].body_text()
        assert not screen.query(ToolCard)  # no generic tool card for todo_write

        screen.sidebar_tab = "todos"
        screen._refresh_sidebar()
        await pilot.pause()
        rendered = "".join(str(child.render()) for child in screen.sidebar.children)
        assert "TODOS · 1/3 done" in rendered and "Run the tests" in rendered
