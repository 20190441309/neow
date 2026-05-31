"""Tests for SessionTree (JSONL-backed tree session storage)."""

import json
import pytest
from pathlib import Path

from neow.core.session_tree import SessionTree


class TestSessionTreeCreate:
    """Tests for creating JSONL sessions."""

    def test_create_makes_jsonl_file(self, tmp_path):
        tree = SessionTree(tmp_path)
        name = tree.create("test-session", "deepseek-chat")
        assert name == "test-session"
        jsonl_path = tmp_path / "test-session.jsonl"
        assert jsonl_path.exists()

    def test_create_writes_meta_header(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("test-session", "deepseek-chat")
        lines = (tmp_path / "test-session.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        meta = json.loads(lines[0])
        assert meta["type"] == "meta"
        assert meta["name"] == "test-session"
        assert meta["model"] == "deepseek-chat"
        assert meta["leafId"] is None
        assert "createdAt" in meta

    def test_create_dir_made(self, tmp_path):
        sessions_dir = tmp_path / "nested" / "sessions"
        tree = SessionTree(sessions_dir)
        tree.create("test", "gpt-4")
        assert sessions_dir.exists()


class TestSessionTreeAppend:
    """Tests for appending messages to a session."""

    def test_append_returns_id(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        entry_id = tree.append("s", "user", "hello")
        assert isinstance(entry_id, str) and len(entry_id) == 32  # uuid4 hex

    def test_append_updates_leaf_id(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        eid = tree.append("s", "user", "hello")
        assert tree.get_leaf_id("s") == eid

    def test_append_chains_parent(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        eid1 = tree.append("s", "user", "hello")
        eid2 = tree.append("s", "assistant", "hi there")
        lines = tree._read_lines("s")
        # Last entry's parentId should be eid1
        entry2 = [e for e in lines if e.get("id") == eid2][0]
        assert entry2["parentId"] == eid1

    def test_append_with_metadata(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        eid = tree.append("s", "tool", "result", metadata={"tool_call_id": "tc_123"})
        lines = tree._read_lines("s")
        entry = [e for e in lines if e.get("id") == eid][0]
        assert entry["metadata"]["tool_call_id"] == "tc_123"

    def test_append_with_explicit_parent(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        eid1 = tree.append("s", "user", "hello")
        eid2 = tree.append("s", "assistant", "hi")
        # Branch: append after eid1 (not eid2)
        eid3 = tree.append("s", "assistant", "alternative", parent_id=eid1)
        lines = tree._read_lines("s")
        entry3 = [e for e in lines if e.get("id") == eid3][0]
        assert entry3["parentId"] == eid1

    def test_append_nonexistent_session_raises(self, tmp_path):
        tree = SessionTree(tmp_path)
        with pytest.raises(FileNotFoundError):
            tree.append("nonexistent", "user", "hello")


class TestSessionTreeGetMessages:
    """Tests for reconstructing conversation from the tree."""

    def test_get_messages_linear(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        tree.append("s", "user", "hello")
        tree.append("s", "assistant", "hi there")
        msgs = tree.get_messages("s")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "hi there"

    def test_get_messages_empty_session(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        msgs = tree.get_messages("s")
        assert msgs == []

    def test_get_messages_nonexistent_session(self, tmp_path):
        tree = SessionTree(tmp_path)
        msgs = tree.get_messages("nonexistent")
        assert msgs == []

    def test_get_messages_follows_leaf(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        eid1 = tree.append("s", "user", "hello")
        eid2 = tree.append("s", "assistant", "response A")
        # Branch from eid1
        eid3 = tree.append("s", "assistant", "response B", parent_id=eid1)
        # Current leaf is eid3, so messages should be hello -> response B
        msgs = tree.get_messages("s")
        assert len(msgs) == 2
        assert msgs[1]["content"] == "response B"

    def test_get_messages_flattens_metadata(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        tree.append("s", "tool", "result", metadata={"tool_call_id": "tc_1"})
        msgs = tree.get_messages("s")
        assert msgs[0]["tool_call_id"] == "tc_1"
        assert msgs[0]["role"] == "tool"


class TestSessionTreeLeafId:
    """Tests for leaf ID management."""

    def test_get_leaf_id_initially_none(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        assert tree.get_leaf_id("s") is None

    def test_set_leaf_id(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        eid = tree.append("s", "user", "hello")
        tree.set_leaf_id("s", eid)
        assert tree.get_leaf_id("s") == eid

    def test_get_leaf_id_nonexistent(self, tmp_path):
        tree = SessionTree(tmp_path)
        assert tree.get_leaf_id("nonexistent") is None


class TestSessionTreeStructure:
    """Tests for tree structure operations."""

    def test_get_tree(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        eid1 = tree.append("s", "user", "hello")
        eid2 = tree.append("s", "assistant", "hi")
        nodes = tree.get_tree("s")
        assert eid1 in nodes
        assert eid2 in nodes
        assert eid1 in nodes[eid2]["children"] or eid2 in nodes[eid1].get("children", [])

    def test_get_tree_content_preview(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        long_content = "x" * 200
        eid = tree.append("s", "user", long_content)
        nodes = tree.get_tree("s")
        assert len(nodes[eid]["content_preview"]) == 80

    def test_get_children(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        eid1 = tree.append("s", "user", "hello")
        eid2 = tree.append("s", "assistant", "hi")
        children = tree.get_children("s", eid1)
        assert eid2 in children

    def test_branch_at(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        eid1 = tree.append("s", "user", "hello")
        eid2 = tree.append("s", "assistant", "response A")
        # Branch back to eid1
        tree.branch_at("s", eid1)
        # Now leaf should point to eid1
        assert tree.get_leaf_id("s") == eid1
        # get_messages should only return the first message
        msgs = tree.get_messages("s")
        assert len(msgs) == 1
        assert msgs[0]["content"] == "hello"

    def test_branch_at_invalid_raises(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        with pytest.raises(ValueError):
            tree.branch_at("s", "nonexistent_id")

    def test_orphan_detection(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        eid1 = tree.append("s", "user", "hello")
        eid2 = tree.append("s", "assistant", "response A")
        eid3 = tree.append("s", "assistant", "response B", parent_id=eid1)
        # Current leaf is eid3. Path from eid3 to root: eid3 -> eid1
        # Target is eid1. Ancestors of eid1: {eid1}
        # Orphans from eid3 path not in target ancestors: {eid3}
        # eid2 is NOT on the current leaf path, so it's not an orphan
        lines = tree._read_lines("s")
        orphans = tree._find_orphans(lines, eid3, eid1)
        assert eid3 in orphans
        assert eid2 not in orphans


class TestSessionTreePersistence:
    """Tests for session persistence and listing."""

    def test_delete_session(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "m")
        assert tree.delete_session("s")
        assert not (tmp_path / "s.jsonl").exists()

    def test_delete_nonexistent(self, tmp_path):
        tree = SessionTree(tmp_path)
        assert not tree.delete_session("nonexistent")

    def test_list_sessions(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("session-a", "m1")
        tree.create("session-b", "m2")
        sessions = tree.list_sessions()
        assert len(sessions) == 2
        names = {s["name"] for s in sessions}
        assert names == {"session-a", "session-b"}

    def test_find_session_exact(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("my-session", "m")
        result = tree.find_session("my-session")
        assert result is not None
        assert result.stem == "my-session"

    def test_find_session_fuzzy(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("my-long-session-name", "m")
        result = tree.find_session("long-session")
        assert result is not None

    def test_find_session_nonexistent(self, tmp_path):
        tree = SessionTree(tmp_path)
        assert tree.find_session("nonexistent") is None


class TestSessionTreeLegacyInterop:
    """Tests for legacy JSON import/export."""

    def test_export_to_legacy(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "deepseek-chat")
        tree.append("s", "user", "hello")
        tree.append("s", "assistant", "hi")
        data = tree.export_to_legacy("s")
        assert data["name"] == "s"
        assert data["model"] == "deepseek-chat"
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][0]["content"] == "hello"

    def test_import_from_legacy(self, tmp_path):
        tree = SessionTree(tmp_path)
        legacy = {
            "name": "old-session",
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
                {"role": "tool", "content": "result", "tool_call_id": "tc_1"},
            ],
        }
        name = tree.import_from_legacy(legacy, "imported")
        assert name == "imported"
        msgs = tree.get_messages("imported")
        assert len(msgs) == 3
        assert msgs[2]["tool_call_id"] == "tc_1"

    def test_roundtrip_legacy(self, tmp_path):
        tree = SessionTree(tmp_path)
        tree.create("s", "mymodel")
        tree.append("s", "user", "question")
        tree.append("s", "assistant", "answer")
        # Export
        data = tree.export_to_legacy("s")
        # Import into a new session
        tree.import_from_legacy(data, "restored")
        # Compare
        msgs = tree.get_messages("restored")
        assert len(msgs) == 2
        assert msgs[0]["content"] == "question"
        assert msgs[1]["content"] == "answer"

    def test_export_nonexistent_raises(self, tmp_path):
        tree = SessionTree(tmp_path)
        with pytest.raises(FileNotFoundError):
            tree.export_to_legacy("nonexistent")
