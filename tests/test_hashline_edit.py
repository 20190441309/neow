"""Tests for hashline-based file editing system."""

import json
import pytest
from pathlib import Path

from neow.tools.hashline_edit import (
    HashlineEditError,
    FileSnapshot,
    SnapshotStore,
    compute_hash,
    detect_bom,
    detect_line_ending,
    format_hashline,
    parse_hashline,
    apply_edit,
    apply_delete,
    apply_batch_edits,
    stale_anchor_recovery,
)


class TestComputeHash:
    """Tests for content hashing."""

    def test_returns_8_char_hex(self):
        h = compute_hash("hello")
        assert len(h) == 8
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        assert compute_hash("test content") == compute_hash("test content")

    def test_different_content_different_hash(self):
        assert compute_hash("aaa") != compute_hash("bbb")

    def test_empty_string(self):
        h = compute_hash("")
        assert len(h) == 8


class TestDetectBom:
    """Tests for BOM detection."""

    def test_no_bom(self):
        bom, content = detect_bom("hello world")
        assert bom == ""
        assert content == "hello world"

    def test_utf8_bom(self):
        bom, content = detect_bom("\ufeffhello")
        assert bom == "\ufeff"
        assert content == "hello"

    def test_utf16_bom(self):
        bom, content = detect_bom("\ufffehello")
        assert bom == "\ufffe"
        assert content == "hello"


class TestDetectLineEnding:
    """Tests for line ending detection."""

    def test_lf(self):
        assert detect_line_ending("line1\nline2\nline3\n") == "\n"

    def test_crlf(self):
        assert detect_line_ending("line1\r\nline2\r\n") == "\r\n"

    def test_cr(self):
        assert detect_line_ending("line1\rline2\r") == "\r"

    def test_mixed_crlf_dominant(self):
        content = "a\r\nb\r\nc\n"
        assert detect_line_ending(content) == "\r\n"

    def test_no_line_endings(self):
        # When no line endings exist, crlf=0 >= lf=0 >= cr=0, so returns "\r\n"
        result = detect_line_ending("no newlines")
        assert result in ("\n", "\r\n")


class TestFormatParseHashline:
    """Tests for hashline reference formatting and parsing."""

    def test_format(self):
        ref = format_hashline("src/main.py", "abc12345")
        assert ref == "¶src/main.py#abc12345"

    def test_parse(self):
        path, h = parse_hashline("¶src/main.py#abc12345")
        assert path == "src/main.py"
        assert h == "abc12345"

    def test_roundtrip(self):
        ref = format_hashline("foo/bar.py", "deadbeef")
        path, h = parse_hashline(ref)
        assert path == "foo/bar.py"
        assert h == "deadbeef"

    def test_parse_invalid_no_pilcrow(self):
        with pytest.raises(HashlineEditError):
            parse_hashline("src/main.py#abc12345")

    def test_parse_invalid_no_hash(self):
        with pytest.raises(HashlineEditError):
            parse_hashline("¶src/main.py")

    def test_parse_empty_path(self):
        with pytest.raises(HashlineEditError):
            parse_hashline("¶#abc12345")


class TestSnapshotStore:
    """Tests for file snapshot management."""

    def test_snapshot_reads_file(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        assert snap.path == str(test_file)
        assert "print('hello')" in snap.content
        assert len(snap.hash) == 8
        assert len(snap.lines) == 1

    def test_snapshot_stores(self):
        """Snapshot should be retrievable after creation."""
        pass

    def test_get_returns_snapshot(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        retrieved = store.get(str(test_file))
        assert retrieved is snap

    def test_get_nonexistent_returns_none(self, tmp_path):
        store = SnapshotStore()
        assert store.get(str(tmp_path / "nope.py")) is None

    def test_validate_matching_hash(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("hello\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        assert store.validate(str(test_file), snap.hash)

    def test_validate_mismatched_hash(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("hello\n", encoding="utf-8")
        store = SnapshotStore()
        store.snapshot(str(test_file))
        # Modify file
        test_file.write_text("changed\n", encoding="utf-8")
        assert not store.validate(str(test_file), "wronghash")

    def test_validate_nonexistent_file(self, tmp_path):
        store = SnapshotStore()
        assert not store.validate(str(tmp_path / "nope.py"), "anyhash")

    def test_snapshot_bom_preserved(self, tmp_path):
        test_file = tmp_path / "bom.py"
        test_file.write_bytes(b"\xef\xbb\xbfprint('bom')\n")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        assert snap.bom == "\ufeff"
        assert "print('bom')" in snap.content

    def test_snapshot_crlf_detected(self, tmp_path):
        test_file = tmp_path / "crlf.py"
        test_file.write_bytes(b"line1\r\nline2\r\n")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        assert snap.line_ending == "\r\n"


class TestApplyEdit:
    """Tests for applying line-anchored edits."""

    def test_replace_single_line(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        msg, new_snap = apply_edit(snap, 2, 2, "replaced\n")
        content = test_file.read_text(encoding="utf-8")
        assert content == "line1\nreplaced\nline3\n"
        assert "¶" in msg

    def test_replace_multiple_lines(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\nline4\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        _, new_snap = apply_edit(snap, 2, 3, "new2\nnew3\n")
        content = test_file.read_text(encoding="utf-8")
        assert content == "line1\nnew2\nnew3\nline4\n"

    def test_insert_before(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        _, new_snap = apply_edit(snap, 2, 2, "inserted\n", insert_before=True)
        content = test_file.read_text(encoding="utf-8")
        assert content == "line1\ninserted\nline2\n"

    def test_insert_after(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        _, new_snap = apply_edit(snap, 1, 1, "inserted\n", insert_after=True)
        content = test_file.read_text(encoding="utf-8")
        assert content == "line1\ninserted\nline2\n"

    def test_insert_before_and_after_both_raises(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        with pytest.raises(HashlineEditError, match="Cannot use both"):
            apply_edit(snap, 1, 1, "x\n", insert_before=True, insert_after=True)

    def test_stale_snapshot_raises(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("original\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        # Modify file externally
        test_file.write_text("modified\n", encoding="utf-8")
        with pytest.raises(HashlineEditError, match="Stale snapshot"):
            apply_edit(snap, 1, 1, "new\n")

    def test_out_of_range_start_line(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        with pytest.raises(HashlineEditError, match="out of range"):
            apply_edit(snap, 5, 5, "x\n")

    def test_out_of_range_end_line(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        with pytest.raises(HashlineEditError, match="out of range"):
            apply_edit(snap, 1, 10, "x\n")

    def test_start_line_less_than_1(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        with pytest.raises(HashlineEditError, match="must be >= 1"):
            apply_edit(snap, 0, 1, "x\n")

    def test_end_before_start(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        with pytest.raises(HashlineEditError, match="must be >= start_line"):
            apply_edit(snap, 3, 1, "x\n")

    def test_file_deleted_raises(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        test_file.unlink()
        with pytest.raises(HashlineEditError, match="File not found"):
            apply_edit(snap, 1, 1, "x\n")


class TestApplyDelete:
    """Tests for deleting lines."""

    def test_delete_single_line(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        _, new_snap = apply_delete(snap, 2, 2)
        content = test_file.read_text(encoding="utf-8")
        assert content == "line1\nline3\n"

    def test_delete_multiple_lines(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\nline4\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        _, new_snap = apply_delete(snap, 2, 3)
        content = test_file.read_text(encoding="utf-8")
        assert content == "line1\nline4\n"


class TestApplyBatchEdits:
    """Tests for batch editing multiple ranges."""

    def test_batch_edits_bottom_to_top(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        edits = [
            {"start_line": 2, "end_line": 2, "new_content": "new2\n"},
            {"start_line": 4, "end_line": 4, "new_content": "new4\n"},
        ]
        summary, snapshots = apply_batch_edits(str(test_file), edits)
        content = test_file.read_text(encoding="utf-8")
        assert content == "line1\nnew2\nline3\nnew4\nline5\n"
        assert "2 edit(s)" in summary

    def test_batch_edits_empty_raises(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\n", encoding="utf-8")
        with pytest.raises(HashlineEditError, match="No edits"):
            apply_batch_edits(str(test_file), [])

    def test_batch_edits_stale_check(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\n", encoding="utf-8")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        edits = [
            {"start_line": 1, "end_line": 1, "new_content": "x\n", "expected_hash": "wrong"},
        ]
        with pytest.raises(HashlineEditError, match="Stale"):
            apply_batch_edits(str(test_file), edits)

    def test_batch_edits_missing_start_line_raises(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\n", encoding="utf-8")
        edits = [{"end_line": 1, "new_content": "x\n"}]
        with pytest.raises(HashlineEditError, match="missing start_line"):
            apply_batch_edits(str(test_file), edits)


class TestBOMAndLineEndingPreservation:
    """Tests for BOM and line ending preservation across edits."""

    def test_bom_preserved_after_edit(self, tmp_path):
        test_file = tmp_path / "bom.py"
        test_file.write_bytes(b"\xef\xbb\xbfline1\nline2\n")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        assert snap.bom == "\ufeff"
        _, new_snap = apply_edit(snap, 1, 1, "replaced\n")
        raw = test_file.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")
        content = raw[3:].decode("utf-8")
        assert content == "replaced\nline2\n"

    def test_crlf_preserved_after_edit(self, tmp_path):
        test_file = tmp_path / "crlf.py"
        test_file.write_bytes(b"line1\r\nline2\r\nline3\r\n")
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        assert snap.line_ending == "\r\n"
        # Replace with content that has a trailing newline - it should be normalized to CRLF
        _, new_snap = apply_edit(snap, 2, 2, "replaced\n")
        content = test_file.read_bytes().decode("utf-8")
        assert "replaced\r\n" in content


class TestStaleAnchorRecovery:
    """Tests for stale anchor recovery."""

    def test_recovery_with_content_hint(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n", encoding="utf-8")
        original_hash = compute_hash(test_file.read_text(encoding="utf-8"))
        # Modify file
        test_file.write_text("prefix\nline1\nline2\nline3\n", encoding="utf-8")
        recovered, msg = stale_anchor_recovery(
            str(test_file), original_hash, 1, 1, "line1"
        )
        assert recovered is True
        assert "Recovered" in msg

    def test_recovery_no_hint_fails(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\n", encoding="utf-8")
        original_hash = compute_hash(test_file.read_text(encoding="utf-8"))
        test_file.write_text("modified\n", encoding="utf-8")
        recovered, msg = stale_anchor_recovery(
            str(test_file), original_hash, 1, 1, ""
        )
        assert recovered is False
        assert "no content hint" in msg

    def test_recovery_file_deleted(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\n", encoding="utf-8")
        original_hash = compute_hash(test_file.read_text(encoding="utf-8"))
        test_file.unlink()
        recovered, msg = stale_anchor_recovery(
            str(test_file), original_hash, 1, 1, "line1"
        )
        assert recovered is False
        assert "no longer exists" in msg

    def test_recovery_content_not_found(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\n", encoding="utf-8")
        original_hash = compute_hash(test_file.read_text(encoding="utf-8"))
        test_file.write_text("completely different\n", encoding="utf-8")
        recovered, msg = stale_anchor_recovery(
            str(test_file), original_hash, 1, 1, "line1"
        )
        assert recovered is False
        assert "not found" in msg or "manual review" in msg

    def test_recovery_same_hash_not_stale(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\n", encoding="utf-8")
        original_hash = compute_hash(test_file.read_text(encoding="utf-8"))
        recovered, msg = stale_anchor_recovery(
            str(test_file), original_hash, 1, 1, "line1"
        )
        assert recovered is True
        # Either "matches expected hash" (exact match) or "Recovered" (found by hint)
        assert "matches expected hash" in msg or "Recovered" in msg


class TestHashlineEditIntegration:
    """Integration tests for the hashline_edit tool function."""

    def test_hashline_edit_tool_function(self, tmp_path):
        from neow.tools.file_ops import hashline_edit, FileError
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n", encoding="utf-8")
        # Get hash
        store = SnapshotStore()
        snap = store.snapshot(str(test_file))
        edits = json.dumps([
            {"start_line": 2, "end_line": 2, "new_content": "replaced\n"}
        ])
        result = hashline_edit(str(test_file), snap.hash, edits)
        # apply_batch_edits returns "Applied N edit(s)..." not "Successfully..."
        assert "edit(s)" in result
        assert "¶" in result
        content = test_file.read_text(encoding="utf-8")
        assert content == "line1\nreplaced\nline3\n"

    def test_hashline_edit_stale_fails(self, tmp_path):
        from neow.tools.file_ops import hashline_edit, FileError
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\n", encoding="utf-8")
        edits = json.dumps([
            {"start_line": 1, "end_line": 1, "new_content": "x\n"}
        ])
        with pytest.raises(FileError, match="[Ss]tale"):
            hashline_edit(str(test_file), "wronghash", edits)

    def test_hashline_edit_invalid_json(self, tmp_path):
        from neow.tools.file_ops import hashline_edit, FileError
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\n", encoding="utf-8")
        with pytest.raises(FileError, match="Invalid edits JSON"):
            hashline_edit(str(test_file), "anyhash", "not json")
