"""File operation tools for Neow CLI."""

from pathlib import Path
from typing import Optional

from neow.utils.logger import logger


class FileError(Exception):
    """File operation error."""

    pass


def read_file(file_path: str) -> str:
    """Read file content.

    Args:
        file_path: Path to the file.

    Returns:
        File content as string.

    Raises:
        FileError: If file cannot be read.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            raise FileError(f"File not found: {file_path}")

        content = path.read_text(encoding="utf-8")
        logger.debug(f"Read file: {file_path}")
        return content
    except FileError:
        raise
    except Exception as e:
        logger.error(f"Failed to read file {file_path}: {e}")
        raise FileError(f"Failed to read file: {e}")


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
