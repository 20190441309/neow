"""Tests for tools."""

import os
import tempfile
from pathlib import Path

import pytest

from neow.tools.file_ops import (
    read_file,
    write_file,
    edit_file,
    FileError
)
from neow.tools.command import execute_command, CommandError


class TestFileOps:
    """Tests for file operation tools."""

    def test_read_file(self, tmp_path):
        """Test reading a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        result = read_file(str(test_file))
        assert result == "Hello, World!"

    def test_read_file_not_found(self):
        """Test reading non-existent file."""
        with pytest.raises(FileError):
            read_file("/nonexistent/file.txt")

    def test_write_file(self, tmp_path):
        """Test writing a file."""
        test_file = tmp_path / "test.txt"

        result = write_file(str(test_file), "Hello, World!")
        assert test_file.read_text() == "Hello, World!"
        assert "successfully" in result.lower()

    def test_write_file_creates_dirs(self, tmp_path):
        """Test writing a file creates parent directories."""
        test_file = tmp_path / "subdir" / "test.txt"

        write_file(str(test_file), "Hello")
        assert test_file.read_text() == "Hello"

    def test_edit_file(self, tmp_path):
        """Test editing a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        result = edit_file(str(test_file), "World", "Python")
        assert test_file.read_text() == "Hello, Python!"
        assert "successfully" in result.lower()

    def test_edit_file_not_found(self):
        """Test editing non-existent file."""
        with pytest.raises(FileError):
            edit_file("/nonexistent/file.txt", "old", "new")

    def test_edit_file_pattern_not_found(self, tmp_path):
        """Test editing file with non-existent pattern."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        with pytest.raises(FileError):
            edit_file(str(test_file), "NotFound", "Replacement")


class TestCommand:
    """Tests for command execution tools."""

    def test_execute_command_success(self):
        """Test executing a successful command."""
        result = execute_command("echo hello")
        assert "hello" in result

    def test_execute_command_with_output(self):
        """Test executing command with output."""
        result = execute_command("python -c \"print('test')\"")
        assert "test" in result

    def test_execute_command_failure(self):
        """Test executing a failing command."""
        with pytest.raises(CommandError):
            execute_command("nonexistent_command")

    def test_execute_command_timeout(self):
        """Test command timeout."""
        with pytest.raises(CommandError):
            execute_command("python -c \"import time; time.sleep(10)\"", timeout=1)
