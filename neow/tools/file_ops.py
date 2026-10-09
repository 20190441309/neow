"""File operation tools for Neow CLI."""

import re
from pathlib import Path
from typing import Optional


from neow.utils.logger import logger
from neow.tools.hashline_edit import compute_hash, format_hashline

class FileError(Exception):
    """File operation error."""

    pass


DEFAULT_READ_LIMIT = 2000
MAX_LINE_CHARS = 2000
_LINE_NUMBER = re.compile(r"^ *\d+\t")


def _looks_binary(raw: bytes) -> bool:
    return b"\x00" in raw[:8192]


def read_file(file_path: str, offset: int = 1, limit: int = DEFAULT_READ_LIMIT) -> str:
    """Read a file as numbered lines (``{n:>6}\\t{line}``).

    Args:
        file_path: Path to the file.
        offset: First line to show (1-indexed).
        limit: Maximum number of lines to show.

    Returns:
        The requested lines, a paging hint when more remain, and the
        ``¶PATH#HASH`` anchor for ``hashline_edit`` (always computed over
        the whole file).

    Raises:
        FileError: If file cannot be read.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            raise FileError(f"File not found: {file_path}")

        raw = path.read_bytes()
        if _looks_binary(raw):
            return f"Binary file ({len(raw)} bytes); not shown: {file_path}"
        content = raw.decode("utf-8")
        anchor = format_hashline(file_path, compute_hash(content))
        logger.debug(f"Read file: {file_path}")
        if not content:
            return f"(empty file)\n{anchor}"

        lines = content.splitlines()
        total = len(lines)
        start = max(int(offset or 1), 1)
        count = max(int(limit or DEFAULT_READ_LIMIT), 1)
        if start > total:
            return (
                f"offset={start} is past the end: {file_path} has only {total} "
                f"lines.\n{anchor}"
            )
        end = min(start + count - 1, total)
        out = []
        for number in range(start, end + 1):
            line = lines[number - 1]
            if len(line) > MAX_LINE_CHARS:
                line = (
                    line[:MAX_LINE_CHARS]
                    + f"… [line truncated, {len(line)} chars]"
                )
            out.append(f"{number:>6}\t{line}")
        if end < total:
            out.append(
                f"… Showing lines {start}-{end} of {total}. "
                f"Use offset={end + 1} to read more."
            )
        out.append(anchor)
        return "\n".join(out)
    except FileError:
        raise
    except Exception as e:
        logger.error(f"Failed to read file {file_path}: {e}")
        raise FileError(f"Failed to read file: {e}")


def _strip_line_numbers(text: str) -> Optional[str]:
    """``text`` without read_file's line-number prefixes, if it has them."""

    lines = text.split("\n")
    if not any(lines) or not all(_LINE_NUMBER.match(ln) for ln in lines if ln):
        return None
    return "\n".join(_LINE_NUMBER.sub("", ln, count=1) for ln in lines)


def write_file(file_path: str, content: str) -> str:
    """Write content to file.

    Args:
        file_path: Path to the file.
        content: Content to write.

    Returns:
        Success message.

    Raises:
        FileError: If file cannot be written.
    """
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.debug(f"Wrote file: {file_path}")
        return f"File written successfully: {file_path}"
    except Exception as e:
        logger.error(f"Failed to write file {file_path}: {e}")
        raise FileError(f"Failed to write file: {e}")


def edit_file(
    file_path: str,
    old_text: str,
    new_text: str,
    first_only: bool = False,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> str:
    """Edit file by replacing text.

    Args:
        file_path: Path to the file.
        old_text: Text to replace.
        new_text: Replacement text.
        first_only: If True, only replace the first occurrence.
        start_line: Start line number (1-indexed, inclusive).
        end_line: End line number (1-indexed, inclusive).

    Returns:
        Success message.

    Raises:
        FileError: If file cannot be edited.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            raise FileError(f"File not found: {file_path}")

        content = path.read_text(encoding="utf-8")

        # Text copied from read_file output may carry its line-number prefixes.
        if old_text not in content:
            stripped = _strip_line_numbers(old_text)
            if stripped is not None and stripped in content:
                old_text = stripped
                new_text = _strip_line_numbers(new_text) or new_text

        # Line-based editing mode
        if start_line is not None or end_line is not None:
            lines = content.splitlines(keepends=True)
            total_lines = len(lines)

            s = (start_line - 1) if start_line else 0
            e = end_line if end_line else total_lines

            if start_line and (s < 0 or s >= total_lines):
                raise FileError(f"start_line {start_line} out of range (1-{total_lines})")
            if end_line and (e < 1 or e > total_lines):
                raise FileError(f"end_line {end_line} out of range (1-{total_lines})")
            if s >= e:
                raise FileError(
                    f"start_line ({start_line}) must be less than end_line ({end_line})"
                )

            region = "".join(lines[s:e])
            if old_text not in region:
                raise FileError(f"old_text not found in lines {start_line}-{end_line}")

            if first_only:
                new_region = region.replace(old_text, new_text, 1)
            else:
                new_region = region.replace(old_text, new_text)
            new_content = "".join(lines[:s]) + new_region + "".join(lines[e:])

            path.write_text(new_content, encoding="utf-8")
            logger.debug(f"Edited file (lines {start_line}-{end_line}): {file_path}")
            return f"File edited successfully: {file_path} (lines {start_line}-{end_line})"

        # Standard text replacement mode
        if old_text not in content:
            raise FileError(f"Text not found in file: {old_text}")

        if first_only:
            new_content = content.replace(old_text, new_text, 1)
        else:
            new_content = content.replace(old_text, new_text)

        path.write_text(new_content, encoding="utf-8")
        logger.debug(f"Edited file: {file_path}")
        count = 1 if first_only else content.count(old_text)
        return f"File edited successfully: {file_path} ({count} replacement{'s' if count != 1 else ''})"
    except FileError:
        raise
    except Exception as e:
        logger.error(f"Failed to edit file {file_path}: {e}")
        raise FileError(f"Failed to edit file: {e}")


def create_file(file_path: str, content: str = "") -> str:
    """Create a new file. Raises FileError if file already exists.

    Args:
        file_path: Path to the file to create.
        content: Initial content (default empty).

    Returns:
        Success message.

    Raises:
        FileError: If file already exists.
    """
    try:
        path = Path(file_path)
        if path.exists():
            raise FileError(f"File already exists: {file_path}. Use write_file to overwrite.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.debug(f"Created file: {file_path}")
        return f"File created successfully: {file_path}"
    except FileError:
        raise
    except Exception as e:
        logger.error(f"Failed to create file {file_path}: {e}")
        raise FileError(f"Failed to create file: {e}")


def delete_file(file_path: str) -> str:
    """Delete a file.

    Args:
        file_path: Path to the file to delete.

    Returns:
        Success message.

    Raises:
        FileError: If file doesn't exist or cannot be deleted.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            raise FileError(f"File not found: {file_path}")
        if not path.is_file():
            raise FileError(f"Not a file: {file_path}")
        path.unlink()
        logger.debug(f"Deleted file: {file_path}")
        return f"File deleted successfully: {file_path}"
    except FileError:
        raise
    except Exception as e:
        logger.error(f"Failed to delete file {file_path}: {e}")
        raise FileError(f"Failed to delete file: {e}")

def hashline_edit(file_path: str, expected_hash: str, edits: str) -> str:
    """Perform hashline-anchored file edits.

    Args:
        file_path: Path to the file.
        expected_hash: Expected hash of file content (8-char hex).
        edits: JSON string of edit operations. Each edit is:
            {"start_line": int, "end_line": int, "new_content": str,
             "insert_before": bool, "insert_after": bool}

    Returns:
        Result message with new file hash.
    """
    import json
    from neow.tools.hashline_edit import (
        SnapshotStore, apply_batch_edits, HashlineEditError, stale_anchor_recovery
    )

    try:
        edit_list = json.loads(edits)
    except json.JSONDecodeError as e:
        raise FileError(f"Invalid edits JSON: {e}")

    store = SnapshotStore()
    snapshot = store.snapshot(file_path)

    if snapshot.hash != expected_hash:
        # Attempt stale recovery for each edit
        for edit in edit_list:
            recovered, msg = stale_anchor_recovery(
                file_path, expected_hash,
                edit.get("start_line", 1), edit.get("end_line", edit.get("start_line", 1)),
                edit.get("old_content_hint", "")
            )
            if not recovered:
                raise FileError(
                    f"Stale anchor: file has been modified since reading (expected {expected_hash}, "
                    f"got {snapshot.hash}). {msg}"
                )

    try:
        result_msg, _snapshots = apply_batch_edits(file_path, edit_list)
        return result_msg
    except HashlineEditError as e:
        raise FileError(str(e))