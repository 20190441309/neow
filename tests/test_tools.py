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
