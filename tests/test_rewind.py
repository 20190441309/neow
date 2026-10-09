"""File checkpoints and /rewind (plan task 5.2)."""

import json

import pytest

from neow.cli.commands import parse_command
from neow.cli.main import setup_tools
from neow.core.agent_loop import AgentLoop
from neow.core.approval import ApprovalMode, ApprovalPolicy
from neow.core.checkpoints import CheckpointStore, rewind_command
from neow.core.conversation import ConversationManager
from neow.core.executor import ToolExecutor
from neow.tui.commands import CommandDispatcher
from tests.test_agent_loop import ScriptedClient, _call


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    (work / "a.py").write_text("v1\n")
    (work / "c.py").write_text("keep me\n")
    executor = ToolExecutor()
    setup_tools(executor)
    executor.approval_policy = ApprovalPolicy(mode=ApprovalMode.YOLO)
    executor.require_read_before_edit = False
    store = CheckpointStore(root=tmp_path / "checkpoints", session_id="s")
    executor.checkpoints = store
    client = ScriptedClient([])
    conv = ConversationManager(client, tool_executor=executor)
    conv.checkpoints = store
    return work, conv, client, store


def _turn(conv, client, prompt, *calls):
    """One user turn in which the model makes *calls* and then answers."""
    client.replies.extend(
        [{"tool_calls": list(calls)}, {"content": f"done: {prompt}"}]
        if calls
        else [{"content": f"done: {prompt}"}]
    )
    list(AgentLoop(conv).run(prompt))


def test_checkpoint_before_first_mutation_in_turn(workspace):
    work, conv, client, store = workspace
    _turn(
        conv,
        client,
        "edit a twice",
        _call("w1", "write_file", file_path="a.py", content="v2\n"),
        _call("w2", "write_file", file_path="a.py", content="v3\n"),
        _call("r1", "read_file", file_path="c.py"),  # reads are not backed up
    )
    (meta,) = store.turns()
    assert meta["prompt"] == "edit a twice"
    assert list(meta["files"]) == [str(work / "a.py")]
    blob = store.dir / "1" / "files" / meta["files"][str(work / "a.py")]
    assert blob.read_text() == "v1\n"  # the state before the turn, not after w1
    assert (work / "a.py").read_text() == "v3\n"


def test_rewind_restores_and_deletes_created_files(workspace):
    work, conv, client, store = workspace
    _turn(
        conv,
        client,
        "first",
        _call("w1", "write_file", file_path="a.py", content="v2\n"),
        _call("c1", "create_file", file_path="sub/b.py", content="new\n"),
    )
    _turn(
        conv,
        client,
        "second",
        _call("w2", "write_file", file_path="a.py", content="v3\n"),
        _call("d1", "delete_file", file_path="c.py"),
    )
    assert not (work / "c.py").exists()

    # Undo only the second turn.
    result = store.rewind(2)
    assert (work / "a.py").read_text() == "v2\n"
    assert (work / "c.py").read_text() == "keep me\n"
    assert (work / "sub" / "b.py").exists()
    assert [m["turn"] for m in store.turns()] == [1]

    # Undo everything since the first turn.
    result = store.rewind(1)
    assert (work / "a.py").read_text() == "v1\n"
    assert not (work / "sub" / "b.py").exists()
    assert result.deleted == [str(work / "sub" / "b.py")]
    assert store.turns() == []
    with pytest.raises(ValueError):
        store.rewind(1)


def test_rewind_conversation_back_to_turn(workspace):
    work, conv, client, store = workspace
    _turn(conv, client, "hello")
    kept = list(conv.messages)
    _turn(
        conv,
        client,
        "change a",
        _call("w1", "write_file", file_path="a.py", content="v2\n"),
    )
    assert len(conv.messages) > len(kept)

    # Conversation only: the file keeps its new content.
    text, kind = rewind_command(store, "2 chat", conv)
    assert conv.messages == kept and kind == "info"
    assert (work / "a.py").read_text() == "v2\n"
    discarded = json.loads((store.dir / "discarded-2.json").read_text())
    assert discarded[-1]["content"] == "done: change a"
    assert "对话已回退" in text

    # The checkpoint is still there, so the files can follow.
    text, _ = rewind_command(store, "#2 files", conv)
    assert (work / "a.py").read_text() == "v1\n"
    assert "已恢复 1 个文件" in text


def test_commands_are_reported_as_not_undoable(workspace):
    work, conv, client, store = workspace
    _turn(
        conv,
        client,
        "run it",
        _call("x1", "execute_command", command="touch made-by-shell.txt"),
    )
    assert "1 条命令" in store.describe()
    text, kind = rewind_command(store, "1", conv)
    assert kind == "warn" and "touch made-by-shell.txt" in text
    assert (work / "made-by-shell.txt").exists()  # really not undone


def test_denied_calls_and_subagents(workspace):
    from neow.core.sub_agent import SubAgent

    work, conv, client, store = workspace
    conv.tool_executor.approval_policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
    conv.tool_executor.approval_callback = lambda *a: False
    _turn(
        conv,
        client,
        "denied",
        _call("w1", "write_file", file_path="a.py", content="x\n"),
    )
    assert store.turns()[0]["files"] == {}  # nothing changed, nothing saved

    conv.tool_executor.approval_policy = ApprovalPolicy(mode=ApprovalMode.YOLO)
    store.begin_turn("delegate", len(conv.messages))
    client.replies.extend(
        [
            {
                "tool_calls": [
                    _call("s1", "write_file", file_path="a.py", content="s\n")
                ]
            },
            {"content": "report"},
        ]
    )
    sub = SubAgent(conv, agent_type="general")
    sub.conversation.tool_executor.require_read_before_edit = False
    assert sub.run("edit a.py") == "report"
    # The sub-agent's edit belongs to the parent's turn; its own run adds none.
    assert [m["prompt"] for m in store.turns()] == ["denied", "delegate"]
    assert str(work / "a.py") in store.turns()[-1]["files"]


def test_old_checkpoints_are_pruned(tmp_path):
    store = CheckpointStore(root=tmp_path, session_id="s", keep_turns=3)
    for i in range(5):
        store.begin_turn(f"turn {i}", i)
    assert [m["turn"] for m in store.turns()] == [3, 4, 5]
    # A new store for the same session continues the numbering.
    again = CheckpointStore(root=tmp_path, session_id="s", keep_turns=3)
    assert again.begin_turn("next", 0) == 6


def test_rewind_command_in_tui_dispatcher(workspace):
    work, conv, client, store = workspace
    _turn(
        conv,
        client,
        "make b",
        _call("c1", "create_file", file_path="b.py", content="b\n"),
    )
    dispatcher = CommandDispatcher(conversation=conv)
    listing = dispatcher.dispatch(parse_command("/rewind")).text
    assert "#1  1 个文件  “make b”" in listing
    assert dispatcher.dispatch(parse_command("/rewind x")).kind == "error"
    assert dispatcher.dispatch(parse_command("/rewind 9")).kind == "error"
    result = dispatcher.dispatch(parse_command("/rewind 1"))
    assert not (work / "b.py").exists() and conv.messages == []
    assert "已删除新建的文件" in result.text
