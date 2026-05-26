"""File operation tools for Neow CLI."""

from pathlib import Path

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


def edit_file(file_path: str, old_text: str, new_text: str) -> str:
    """Edit file by replacing text.

    Args:
        file_path: Path to the file.
        old_text: Text to replace.
        new_text: Replacement text.

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

        if old_text not in content:
            raise FileError(f"Text not found in file: {old_text}")

        new_content = content.replace(old_text, new_text)
        path.write_text(new_content, encoding="utf-8")
        logger.debug(f"Edited file: {file_path}")
        return f"File edited successfully: {file_path}"
    except FileError:
        raise
    except Exception as e:
        logger.error(f"Failed to edit file {file_path}: {e}")
        raise FileError(f"Failed to edit file: {e}")
