"""Tests for utility modules."""

import logging

from unittest.mock import patch

from neow.utils.logger import setup_logger


class TestLogger:
    """Tests for logger setup."""

    def test_setup_logger_default(self):
        """Test default logger setup."""
        logger = setup_logger("test_default")
        assert logger.name == "test_default"
        assert logger.level == logging.INFO
        assert len(logger.handlers) >= 1

    def test_setup_logger_custom_level(self):
        """Test logger with custom level."""
        logger = setup_logger("test_debug", level=logging.DEBUG)
        assert logger.level == logging.DEBUG

    def test_setup_logger_with_file(self, tmp_path):
        """Test logger with file handler."""
        log_file = tmp_path / "test.log"
        logger = setup_logger("test_file", log_file=log_file)
        assert len(logger.handlers) >= 2
        assert log_file.parent.exists()

    def test_setup_logger_creates_parent_dirs(self, tmp_path):
        """Test logger creates parent directories for log file."""
        log_file = tmp_path / "subdir" / "test.log"
        setup_logger("test_dirs", log_file=log_file)
        assert log_file.parent.exists()

    def test_logger_writes_to_file(self, tmp_path):
        """Test logger actually writes to file."""
        log_file = tmp_path / "test.log"
        logger = setup_logger("test_write", log_file=log_file, level=logging.DEBUG)
        logger.info("Test message")
        # Flush handlers
        for handler in logger.handlers:
            handler.flush()
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "Test message" in content


class TestFormatter:
    """Tests for formatter functions."""

    @patch("neow.utils.formatter.console")
    def test_print_user_message(self, mock_console):
        """Test user message formatting."""
        from neow.utils.formatter import print_user_message
        from rich.panel import Panel

        print_user_message("Hello")
        mock_console.print.assert_called_once()
        args = mock_console.print.call_args[0][0]
        assert isinstance(args, Panel)

    @patch("neow.utils.formatter.console")
    def test_print_assistant_message(self, mock_console):
        """Test assistant message formatting."""
        from neow.utils.formatter import print_assistant_message
        from rich.panel import Panel

        print_assistant_message("Hi there")
        mock_console.print.assert_called_once()
        args = mock_console.print.call_args[0][0]
        assert isinstance(args, Panel)

    @patch("neow.utils.formatter.console")
    def test_print_tool_call(self, mock_console):
        """Test tool call formatting."""
        from neow.utils.formatter import print_tool_call
        from rich.panel import Panel

        print_tool_call("search", {"query": "test"})
        assert mock_console.print.call_count == 1
        args = mock_console.print.call_args[0][0]
        assert isinstance(args, Panel)

    @patch("neow.utils.formatter.console")
    def test_print_tool_result_success(self, mock_console):
        """Test tool result formatting for success."""
        from neow.utils.formatter import print_tool_result
        from rich.panel import Panel

        print_tool_result("result data")
        assert mock_console.print.call_count == 1
        args = mock_console.print.call_args[0][0]
        assert isinstance(args, Panel)

    @patch("neow.utils.formatter.console")
    def test_print_tool_result_error(self, mock_console):
        """Test tool result formatting for error."""
        from neow.utils.formatter import print_tool_result
        from rich.panel import Panel

        print_tool_result("error occurred", is_error=True)
        assert mock_console.print.call_count == 1
        args = mock_console.print.call_args[0][0]
        assert isinstance(args, Panel)

    @patch("neow.utils.formatter.console")
    def test_print_error(self, mock_console):
        """Test error message formatting."""
        from neow.utils.formatter import print_error
        from rich.panel import Panel

        print_error("Something went wrong")
        mock_console.print.assert_called_once()
        args = mock_console.print.call_args[0][0]
        assert isinstance(args, Panel)

    @patch("neow.utils.formatter.console")
    def test_print_warning(self, mock_console):
        """Test warning message formatting."""
        from neow.utils.formatter import print_warning

        print_warning("Be careful")
        mock_console.print.assert_called_once()
        args = mock_console.print.call_args[0][0]
        assert "Warning:" in args

    @patch("neow.utils.formatter.console")
    def test_print_info(self, mock_console):
        """Test info message formatting."""
        from neow.utils.formatter import print_info

        print_info("FYI")
        mock_console.print.assert_called_once()
        args = mock_console.print.call_args[0][0]
        assert "Info:" in args
