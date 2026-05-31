"""Hashline-based file editing system.

Provides precise file editing anchored by content hashes, preventing stale edits.
Uses the ¶PATH#HASH canonical reference format.
"""

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class HashlineEditError(Exception):
    """Error in hashline editing."""
    pass


@dataclass
class FileSnapshot:
    """Represents a snapshot of a file at a point in time."""
    path: str          # File path
    hash: str          # Content hash (8-char hex)
    content: str       # Full file content
    lines: List[str]   # Split lines (with line endings preserved)
    bom: str           # BOM prefix if present ("\ufeff" or "")
    line_ending: str   # Detected line ending: "\n", "\r\n", or "\r"
    timestamp: float   # mtime when read


def compute_hash(content: str) -> str:
    """Compute short hash of content.

    Uses hashlib.sha256, takes first 8 hex chars.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]


def detect_bom(content: str) -> Tuple[str, str]:
    """Detect and strip BOM from content.

    Returns (bom, stripped_content).
    """
    # UTF-8 BOM: EF BB BF (U+FEFF)
    if content.startswith("\ufeff"):
        return "\ufeff", content[1:]
    # UTF-16 BE BOM: FE FF
    if content.startswith("\ufffe"):
        return "\ufffe", content[1:]
    # UTF-32 BE BOM: 00 00 FE FF — Python decodes to U+FEFF at start
    # Already handled above since Python reads as single char.
    return "", content


def detect_line_ending(content: str) -> str:
    """Detect dominant line ending in content.

    Counts \\r\\n vs standalone \\n vs standalone \\r. Returns the most common.
    Defaults to \\n if no line endings found.
    """
    crlf = content.count("\r\n")
    # Count standalone \n (not preceded by \r)
    lf = 0
    for i, ch in enumerate(content):
        if ch == "\n" and (i == 0 or content[i - 1] != "\r"):
            lf += 1
    # Count standalone \r (not followed by \n)
    cr = 0
    for i, ch in enumerate(content):
        if ch == "\r" and (i == len(content) - 1 or content[i + 1] != "\n"):
            cr += 1

    if crlf >= lf and crlf >= cr:
        return "\r\n"
    if lf >= cr:
        return "\n"
    return "\r"


def format_hashline(path: str, hash: str) -> str:
    """Format a ¶PATH#HASH reference."""
    return f"\u00b6{path}#{hash}"


def parse_hashline(ref: str) -> Tuple[str, str]:
    """Parse a ¶PATH#HASH reference.

    Returns (path, hash).
    Raises HashlineEditError if format is invalid.
    """
    if not ref.startswith("\u00b6"):
        raise HashlineEditError(f"Invalid hashline reference: {ref!r}")
    body = ref[1:]  # Strip ¶
    if "#" not in body:
        raise HashlineEditError(f"Missing hash separator in reference: {ref!r}")
    path, hash_val = body.split("#", 1)
    if not path or not hash_val:
        raise HashlineEditError(f"Empty path or hash in reference: {ref!r}")
    return path, hash_val


def _split_lines_preserving(content: str) -> List[str]:
    """Split content into lines preserving line endings.

    Handles the common case where the last line has no trailing newline.
    """
    if not content:
        return []
    lines = content.splitlines(True)
    # splitlines(True) drops a trailing empty string if content ends with \n,
    # but keeps lines without endings. That's exactly what we want.
    return lines


class SnapshotStore:
    """In-memory store of file snapshots for hashline editing."""

    def __init__(self):
        self._snapshots: Dict[str, FileSnapshot] = {}

    def snapshot(self, file_path: str) -> FileSnapshot:
        """Read file and create snapshot.

        Replaces any previous snapshot for this path.
        """
        path = Path(file_path)
        if not path.exists():
            raise HashlineEditError(f"File not found: {file_path}")

        try:
            raw = path.read_bytes()
        except Exception as e:
            raise HashlineEditError(f"Failed to read file {file_path}: {e}")

        # Detect BOM before decoding
        bom = ""
        if raw.startswith(b"\xef\xbb\xbf"):
            bom = "\ufeff"
            raw = raw[3:]
        elif raw.startswith(b"\xff\xfe"):
            bom = "\ufffe"
            raw = raw[2:]

        content = raw.decode("utf-8")
        line_ending = detect_line_ending(content)
        content_hash = compute_hash(bom + content)
        lines = _split_lines_preserving(content)

        try:
            stat = path.stat()
            timestamp = stat.st_mtime
        except Exception:
            timestamp = time.time()

        snap = FileSnapshot(
            path=file_path,
            hash=content_hash,
            content=bom + content,
            lines=lines,
            bom=bom,
            line_ending=line_ending,
            timestamp=timestamp,
        )
        self._snapshots[file_path] = snap
        return snap

    def get(self, file_path: str) -> Optional[FileSnapshot]:
        """Get existing snapshot without re-reading."""
        return self._snapshots.get(file_path)

    def validate(self, file_path: str, expected_hash: str) -> bool:
        """Validate that current file content matches expected hash."""
        path = Path(file_path)
        if not path.exists():
            return False
        try:
            raw = path.read_bytes()
            bom = ""
            if raw.startswith(b"\xef\xbb\xbf"):
                bom = "\ufeff"
                raw = raw[3:]
            elif raw.startswith(b"\xff\xfe"):
                bom = "\ufffe"
                raw = raw[2:]
            content = raw.decode("utf-8")
            current_hash = compute_hash(bom + content)
            return current_hash == expected_hash
        except Exception:
            return False


def _normalize_line_ending(text: str, target_ending: str) -> str:
    """Normalize all line endings in text to the target ending."""
    # First normalize to \n, then convert to target
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if target_ending == "\n":
        return normalized
    return normalized.replace("\n", target_ending)


def apply_edit(
    snapshot: FileSnapshot,
    start_line: int,
    end_line: int,
    new_content: str,
    *,
    insert_before: bool = False,
    insert_after: bool = False,
) -> Tuple[str, FileSnapshot]:
    """Apply a line-anchored edit to a file snapshot.

    Args:
        snapshot: The file snapshot to edit.
        start_line: 1-indexed start line.
        end_line: 1-indexed end line (inclusive; same as start_line for single line).
        new_content: Replacement content (can be multi-line).
        insert_before: Insert before start_line instead of replacing.
        insert_after: Insert after end_line instead of replacing.

    Returns:
        (result_message, new_snapshot)

    Raises:
        HashlineEditError: If lines out of range or file hash doesn't match.
    """
    if insert_before and insert_after:
        raise HashlineEditError("Cannot use both insert_before and insert_after")

    path = Path(snapshot.path)

    # Re-read file and verify hash
    if not path.exists():
        raise HashlineEditError(f"File not found: {snapshot.path}")

    raw = path.read_bytes()
    bom = ""
    if raw.startswith(b"\xef\xbb\xbf"):
        bom = "\ufeff"
        raw = raw[3:]
    elif raw.startswith(b"\xff\xfe"):
        bom = "\ufffe"
        raw = raw[2:]

    content = raw.decode("utf-8")
    current_hash = compute_hash(bom + content)

    if current_hash != snapshot.hash:
        raise HashlineEditError(
            f"Stale snapshot for {snapshot.path}: expected {snapshot.hash}, "
            f"got {current_hash}. File has been modified since it was read."
        )

    lines = _split_lines_preserving(content)
    num_lines = len(lines)

    # Validate line ranges
    if start_line < 1:
        raise HashlineEditError(f"start_line must be >= 1, got {start_line}")
    if end_line < start_line:
        raise HashlineEditError(
            f"end_line ({end_line}) must be >= start_line ({start_line})"
        )

    if insert_before:
        if start_line > num_lines + 1:
            raise HashlineEditError(
                f"start_line {start_line} is out of range (file has {num_lines} lines)"
            )
    elif insert_after:
        if end_line > num_lines:
            raise HashlineEditError(
                f"end_line {end_line} is out of range (file has {num_lines} lines)"
            )
    else:
        if start_line > num_lines:
            raise HashlineEditError(
                f"start_line {start_line} is out of range (file has {num_lines} lines)"
            )
        if end_line > num_lines:
            raise HashlineEditError(
                f"end_line {end_line} is out of range (file has {num_lines} lines)"
            )

    line_ending = detect_line_ending(content)

    # Normalize new_content to use the same line ending
    if new_content:
        normalized_new = _normalize_line_ending(new_content, line_ending)
    else:
        normalized_new = ""

    # Build new lines
    # Python 0-indexed: start_line-1 .. end_line-1
    s = start_line - 1
    e = end_line  # exclusive end for slicing

    if insert_before:
        # Insert new_content before start_line
        new_lines_text = _split_lines_preserving(normalized_new)
        # Ensure inserted content ends with a line ending so it separates from existing line
        if new_lines_text and not new_lines_text[-1].endswith(("\n", "\r\n", "\r")):
            new_lines_text[-1] += line_ending
        result_lines = lines[:s] + new_lines_text + lines[s:]
        action = "inserted before"
        affected = f"line {start_line}"
    elif insert_after:
        # Insert new_content after end_line
        new_lines_text = _split_lines_preserving(normalized_new)
        if new_lines_text and not new_lines_text[-1].endswith(("\n", "\r\n", "\r")):
            new_lines_text[-1] += line_ending
        result_lines = lines[:e] + new_lines_text + lines[e:]
        action = "inserted after"
        affected = f"line {end_line}"
    else:
        # Replace lines s..e-1 with new_content
        new_lines_text = _split_lines_preserving(normalized_new)
        result_lines = lines[:s] + new_lines_text + lines[e:]
        action = "replaced"
        affected = f"lines {start_line}-{end_line}" if start_line != end_line else f"line {start_line}"

    # Reassemble content
    new_content_full = "".join(result_lines)

    # Write back with BOM preserved
    write_content = bom + new_content_full
    try:
        path.write_bytes(write_content.encode("utf-8"))
    except Exception as ex:
        raise HashlineEditError(f"Failed to write file {snapshot.path}: {ex}")

    # Create new snapshot
    new_hash = compute_hash(write_content)
    new_lines = _split_lines_preserving(new_content_full)

    try:
        stat = path.stat()
        timestamp = stat.st_mtime
    except Exception:
        timestamp = time.time()

    new_snap = FileSnapshot(
        path=snapshot.path,
        hash=new_hash,
        content=write_content,
        lines=new_lines,
        bom=bom,
        line_ending=line_ending,
        timestamp=timestamp,
    )

    result_msg = (
        f"Successfully {action} {affected} in {snapshot.path}. "
        f"{format_hashline(snapshot.path, new_hash)}"
    )
    return result_msg, new_snap


def apply_delete(
    snapshot: FileSnapshot,
    start_line: int,
    end_line: int,
) -> Tuple[str, FileSnapshot]:
    """Delete lines from start_line to end_line (inclusive).

    Returns (result_message, new_snapshot).
    """
    # A delete is a replace with empty content
    return apply_edit(snapshot, start_line, end_line, "")


def apply_batch_edits(
    file_path: str,
    edits: List[Dict],
) -> Tuple[str, List[FileSnapshot]]:
    """Apply multiple edits to a single file.

    Edits are applied from bottom to top (highest line numbers first) so that
    earlier line numbers remain valid after each edit.

    Args:
        file_path: Path to the file.
        edits: List of edit dicts. Each has:
            - start_line (int): 1-indexed start line.
            - end_line (int): 1-indexed end line (inclusive).
            - new_content (str): Replacement content.
            - insert_before (bool, optional): Insert before start_line.
            - insert_after (bool, optional): Insert after end_line.
            - expected_hash (str, optional): Expected file hash for stale detection.

    Returns:
        (summary_message, list_of_snapshots_after_each_edit)
    """
    if not edits:
        raise HashlineEditError("No edits provided")

    store = SnapshotStore()
    snap = store.snapshot(file_path)

    # Check stale on first edit if expected_hash provided
    first_hash = edits[0].get("expected_hash")
    if first_hash and snap.hash != first_hash:
        raise HashlineEditError(
            f"Stale snapshot for {file_path}: expected {first_hash}, got {snap.hash}"
        )

    # Sort edits by start_line descending (bottom to top)
    sorted_edits = sorted(
        enumerate(edits),
        key=lambda x: x[1].get("start_line", 0),
        reverse=True,
    )

    snapshots: List[FileSnapshot] = []
    messages: List[str] = []

    for _orig_idx, edit in sorted_edits:
        start = edit.get("start_line")
        end = edit.get("end_line", start)
        new_content = edit.get("new_content", "")
        insert_before = edit.get("insert_before", False)
        insert_after = edit.get("insert_after", False)

        if start is None:
            raise HashlineEditError(f"Edit missing start_line: {edit}")

        msg, snap = apply_edit(
            snap,
            start,
            end,
            new_content,
            insert_before=insert_before,
            insert_after=insert_after,
        )
        snapshots.append(snap)
        messages.append(msg)

    # Return in chronological order (reverse of application order)
    snapshots.reverse()
    messages.reverse()

    summary = f"Applied {len(edits)} edit(s) to {file_path}."
    if snapshots:
        summary += f" Final: {format_hashline(file_path, snapshots[-1].hash)}"
    return summary, snapshots


def stale_anchor_recovery(
    file_path: str,
    expected_hash: str,
    start_line: int,
    end_line: int,
    old_content_hint: str = "",
) -> Tuple[bool, str]:
    """Attempt to recover from a stale anchor.

    Strategies:
    1. Re-read the file and try to find old_content_hint if provided.
    2. If found, return (True, message_with_new_line_numbers).
    3. If not found, return (False, error_message).

    Returns:
        (recovered, message)
    """
    path = Path(file_path)
    if not path.exists():
        return False, f"File {file_path} no longer exists"

    try:
        raw = path.read_bytes()
        bom = ""
        if raw.startswith(b"\xef\xbb\xbf"):
            bom = "\ufeff"
            raw = raw[3:]
        elif raw.startswith(b"\xff\xfe"):
            bom = "\ufffe"
            raw = raw[2:]
        content = raw.decode("utf-8")
    except Exception as e:
        return False, f"Cannot read file {file_path}: {e}"

    current_hash = compute_hash(bom + content)
    if current_hash == expected_hash:
        # Not actually stale
        return True, f"File matches expected hash at lines {start_line}-{end_line}"

    if not old_content_hint:
        return (
            False,
            f"File has been modified (expected {expected_hash}, got {current_hash}) "
            f"and no content hint provided to locate new position",
        )

    # Search for the old content hint in the current file
    lines = _split_lines_preserving(content)
    hint_normalized = old_content_hint.rstrip("\r\n")

    # Try exact multi-line match
    search_text = "".join(lines)
    hint_idx = search_text.find(old_content_hint)
    if hint_idx == -1:
        # Try without trailing whitespace differences
        hint_idx = search_text.find(hint_normalized)
    if hint_idx == -1:
        # Try line-by-line match for the hint
        hint_lines = old_content_hint.splitlines()
        if hint_lines:
            first_hint = hint_lines[0].strip()
            for i, line in enumerate(lines):
                if first_hint and first_hint in line.strip():
                    # Found a candidate; verify subsequent lines
                    match = True
                    for j, hl in enumerate(hint_lines):
                        if i + j >= len(lines):
                            match = False
                            break
                        if hl.strip() not in lines[i + j].strip():
                            match = False
                            break
                    if match:
                        new_start = i + 1  # 1-indexed
                        new_end = i + len(hint_lines)
                        return (
                            True,
                            f"Recovered: content found at lines {new_start}-{new_end}",
                        )
        return (
            False,
            f"Content hint not found in current file; manual review needed. "
            f"File hash changed from {expected_hash} to {current_hash}.",
        )

    # Compute line number from character offset
    new_start = search_text[:hint_idx].count("\n") + 1
    hint_lines_count = old_content_hint[:len(old_content_hint)].count("\n") + 1
    new_end = new_start + hint_lines_count - 1

    return (
        True,
        f"Recovered: content found at lines {new_start}-{new_end}",
    )
