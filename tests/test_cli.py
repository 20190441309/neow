"""Tests for CLI modules."""

from unittest.mock import MagicMock, patch

import pytest

from neow.cli.commands import parse_command, Command


class TestCommands:
    """Tests for command parsing."""

    def test_parse_help_command(self):
        """Test parsing help command."""
        result = parse_command("/help")
        assert result.command == Command.HELP

    def test_parse_clear_command(self):
        """Test parsing clear command."""
        result = parse_command("/clear")
        assert result.command == Command.CLEAR

    def test_parse_exit_command(self):
        """Test parsing exit command."""
        result = parse_command("/exit")
        assert result.command == Command.EXIT

    def test_parse_model_command(self):
        """Test parsing model command."""
        result = parse_command("/model deepseek")
        assert result.command == Command.MODEL
        assert result.args == "deepseek"

    def test_parse_invalid_command(self):
        """Test parsing invalid command."""
        result = parse_command("not a command")
        assert result.command is None

    def test_parse_empty_input(self):
        """Test parsing empty input."""
        result = parse_command("")
        assert result.command is None
