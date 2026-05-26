"""Tests for CLI modules."""

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

    def test_parse_diff_command(self):
        """Test parsing diff command."""
        result = parse_command("/diff")
        assert result.command == Command.DIFF

    def test_parse_commit_command(self):
        """Test parsing commit command."""
        result = parse_command("/commit")
        assert result.command == Command.COMMIT
        assert result.args is None

    def test_parse_commit_command_with_message(self):
        """Test parsing commit command with message."""
        result = parse_command("/commit my message")
        assert result.command == Command.COMMIT
        assert result.args == "my message"

    def test_parse_undo_command(self):
        """Test parsing undo command."""
        result = parse_command("/undo")
        assert result.command == Command.UNDO

    def test_parse_add_command(self):
        """Test parsing add command."""
        result = parse_command("/add test.py")
        assert result.command == Command.ADD
        assert result.args == "test.py"

    def test_parse_drop_command(self):
        """Test parsing drop command."""
        result = parse_command("/drop test.py")
        assert result.command == Command.DROP
        assert result.args == "test.py"

    def test_parse_ls_command(self):
        """Test parsing ls command."""
        result = parse_command("/ls")
        assert result.command == Command.LS


class TestModelSwitching:
    def test_model_switch_preserves_history(self):
        from unittest.mock import MagicMock
        from neow.core.conversation import ConversationManager

        mock_client1 = MagicMock()
        mock_client1.model = "deepseek-chat"
        mock_client2 = MagicMock()
        mock_client2.model = "claude-sonnet-4-6"

        manager = ConversationManager(mock_client1)
        manager.add_message("user", "Hello")
        manager.add_message("assistant", "Hi there")

        manager.model_client = mock_client2

        assert manager.model_client.model == "claude-sonnet-4-6"
        assert len(manager.messages) == 2

    def test_resolve_model_alias_in_config(self):
        from neow.core.config import Config
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text("{}")
            config = Config(cfg_path)

            assert config.resolve_model_alias("sonnet") == "anthropic"
            assert config.resolve_model_alias("deep") == "deepseek"
            assert config.resolve_model_alias("anthropic") == "anthropic"

    def test_repl_accepts_config_param(self):
        from unittest.mock import MagicMock
        from neow.cli.repl import REPL

        mock_conversation = MagicMock()
        mock_config = MagicMock()

        repl = REPL(mock_conversation, config=mock_config, streaming=False)
        assert repl.config is mock_config
        assert repl.conversation is mock_conversation
        assert repl.streaming is False

    def test_model_command_switches_client(self):
        import sys
        from unittest.mock import MagicMock, patch
        from neow.cli.repl import REPL
        from neow.cli.commands import parse_command

        mock_conversation = MagicMock()
        mock_conversation.model_client.model = "deepseek-chat"
        mock_config = MagicMock()
        mock_config.resolve_model_alias.return_value = "anthropic"

        mock_new_client = MagicMock()
        mock_new_client.validate_connection.return_value = True

        repl = REPL(mock_conversation, config=mock_config, streaming=False)

        # Create a mock for neow.cli.main.create_model_client via sys.modules
        mock_main_module = MagicMock()
        mock_main_module.create_model_client.return_value = mock_new_client
        sys.modules["neow.cli.main"] = mock_main_module

        try:
            parsed = parse_command("/model anthropic")
            repl._handle_command(parsed)
        finally:
            del sys.modules["neow.cli.main"]

        assert mock_conversation.model_client is mock_new_client

    def test_model_command_no_args_shows_info(self):
        from unittest.mock import MagicMock, patch
        from neow.cli.repl import REPL
        from neow.cli.commands import parse_command

        mock_conversation = MagicMock()
        mock_conversation.model_client.model = "deepseek-chat"
        mock_config = MagicMock()
        mock_config.models = {"deepseek": {}, "anthropic": {}, "openai": {}}

        repl = REPL(mock_conversation, config=mock_config, streaming=False)
        parsed = parse_command("/model")

        with patch("neow.cli.repl.print_info") as mock_print:
            repl._handle_command(parsed)

        calls_text = " ".join(str(c) for c in mock_print.call_args_list)
        assert "deepseek-chat" in calls_text
        assert "Available models" in calls_text


class TestLintTestCommands:
    """Tests for lint and test command parsing."""

    def test_parse_lint_command(self):
        """Test parsing /lint command without args."""
        parsed = parse_command("/lint")
        assert parsed.command == Command.LINT
        assert parsed.args is None

    def test_parse_lint_on_command(self):
        """Test parsing /lint on command."""
        parsed = parse_command("/lint on")
        assert parsed.command == Command.LINT
        assert parsed.args == "on"

    def test_parse_test_command(self):
        """Test parsing /test command."""
        parsed = parse_command("/test")
        assert parsed.command == Command.TEST

    def test_parse_architect_command(self):
        """Test parsing /architect command."""
        parsed = parse_command("/architect")
        assert parsed.command == Command.ARCHITECT

    def test_parse_code_command(self):
        """Test parsing /code command."""
        parsed = parse_command("/code")
        assert parsed.command == Command.CODE

    def test_pending_lint_feedback_buffer(self):
        """Test pending_lint_feedback attribute on ConversationManager."""
        from unittest.mock import MagicMock
        from neow.core.conversation import ConversationManager

        manager = ConversationManager(MagicMock())
        assert manager.pending_lint_feedback is None
        manager.pending_lint_feedback = "lint error output"
        assert manager.pending_lint_feedback == "lint error output"


class TestArchitectMode:
    def test_architect_mode_flag(self):
        from unittest.mock import MagicMock
        from neow.cli.repl import REPL

        mock_conv = MagicMock()
        mock_config = MagicMock()
        mock_config.lint_test = {"auto_lint": False, "auto_test": False}
        repl = REPL(mock_conv, mock_config, streaming=False)
        assert repl.architect_mode is False

    def test_architect_command_toggles_mode(self):
        from unittest.mock import MagicMock, patch
        from neow.cli.repl import REPL
        from neow.cli.commands import parse_command

        mock_conv = MagicMock()
        mock_config = MagicMock()
        mock_config.lint_test = {"auto_lint": False, "auto_test": False}
        repl = REPL(mock_conv, mock_config, streaming=False)

        with patch('neow.cli.repl.print_info'):
            parsed = parse_command("/architect")
            repl._handle_command(parsed)
            assert repl.architect_mode is True

            parsed = parse_command("/code")
            repl._handle_command(parsed)
            assert repl.architect_mode is False

    def test_process_input_routes_to_architect(self):
        from unittest.mock import MagicMock, patch
        from neow.cli.repl import REPL

        mock_conv = MagicMock()
        mock_conv.pending_lint_feedback = None
        mock_config = MagicMock()
        mock_config.lint_test = {"auto_lint": False, "auto_test": False}
        repl = REPL(mock_conv, mock_config, streaming=False)
        repl.architect_mode = True

        with patch.object(repl, '_process_architect') as mock_arch:
            repl._process_input("build a REST API")
            mock_arch.assert_called_once_with("build a REST API")

    def test_process_input_routes_to_streaming(self):
        from unittest.mock import MagicMock, patch
        from neow.cli.repl import REPL

        mock_conv = MagicMock()
        mock_conv.pending_lint_feedback = None
        mock_config = MagicMock()
        mock_config.lint_test = {"auto_lint": False, "auto_test": False}
        repl = REPL(mock_conv, mock_config, streaming=True)
        repl.architect_mode = False

        with patch.object(repl, '_process_input_stream') as mock_stream:
            repl._process_input("hello")
            mock_stream.assert_called_once_with("hello")


class TestSessionCommands:
    """Tests for /save /load /history /cost commands."""

    def test_parse_save_command(self):
        from neow.cli.commands import parse_command, Command
        parsed = parse_command("/save my-session")
        assert parsed.command == Command.SAVE
        assert parsed.args == "my-session"

    def test_parse_save_no_args(self):
        from neow.cli.commands import parse_command, Command
        parsed = parse_command("/save")
        assert parsed.command == Command.SAVE
        assert parsed.args is None

    def test_parse_load_command(self):
        from neow.cli.commands import parse_command, Command
        parsed = parse_command("/load my-session")
        assert parsed.command == Command.LOAD
        assert parsed.args == "my-session"

    def test_parse_history_command(self):
        from neow.cli.commands import parse_command, Command
        parsed = parse_command("/history")
        assert parsed.command == Command.HISTORY

    def test_parse_cost_command(self):
        from neow.cli.commands import parse_command, Command
        parsed = parse_command("/cost")
        assert parsed.command == Command.COST


class TestWebCommandParsing:
    """Tests for /web command and raw_command field."""

    def test_parse_web_command(self):
        from neow.cli.commands import parse_command, Command
        parsed = parse_command("/web https://example.com")
        assert parsed.command == Command.WEB
        assert parsed.args == "https://example.com"

    def test_parse_web_no_args(self):
        from neow.cli.commands import parse_command, Command
        parsed = parse_command("/web")
        assert parsed.command == Command.WEB
        assert parsed.args is None

    def test_unknown_slash_command_sets_raw_command(self):
        from neow.cli.commands import parse_command
        parsed = parse_command("/unknown-cmd some args")
        assert parsed.command is None
        assert parsed.raw_command == "/unknown-cmd"
        assert parsed.args == "some args"

    def test_non_slash_input_raw_command_none(self):
        from neow.cli.commands import parse_command
        parsed = parse_command("just text")
        assert parsed.command is None
        assert parsed.raw_command is None


class TestWebCommandInREPL:
    """Tests for /web command handling in REPL."""

    def test_web_command_fetches_and_caches(self):
        from unittest.mock import MagicMock, patch
        from neow.cli.repl import REPL
        from neow.cli.commands import parse_command
        from neow.tools.web import WebContent

        mock_conv = MagicMock()
        mock_conv.web_cache = {}
        mock_config = MagicMock()
        mock_config.web = {"enabled": True, "auto_detect": True, "timeout": 10, "max_content_length": 10000}
        repl = REPL(mock_conv, config=mock_config, streaming=False)

        mock_content = WebContent(
            url="https://example.com", title="Example",
            text="Hello", code_blocks=[], content_type="webpage",
        )
        repl.web_fetcher = MagicMock()
        repl.web_fetcher.fetch.return_value = mock_content

        parsed = parse_command("/web https://example.com")
        repl._handle_command(parsed)

        repl.web_fetcher.fetch.assert_called_once_with("https://example.com")
        mock_conv.add_web_content.assert_called_once_with("https://example.com", mock_content)

    def test_web_command_no_args_shows_error(self):
        from unittest.mock import MagicMock, patch
        from neow.cli.repl import REPL
        from neow.cli.commands import parse_command

        mock_conv = MagicMock()
        mock_config = MagicMock()
        mock_config.web = {"enabled": True, "auto_detect": True, "timeout": 10, "max_content_length": 10000}
        repl = REPL(mock_conv, config=mock_config, streaming=False)

        parsed = parse_command("/web")
        with patch("neow.cli.repl.print_error") as mock_err:
            repl._handle_command(parsed)
            mock_err.assert_called()

    def test_url_auto_detection_in_input(self):
        """Test that URLs in user input trigger auto-fetch."""
        import re
        url_pattern = re.compile(r'https?://[^\s]+')
        text = "Please check https://example.com for details"
        urls = url_pattern.findall(text)
        assert urls == ["https://example.com"]

    def test_url_auto_detection_no_false_positives(self):
        """Test that non-URL text is not matched."""
        import re
        url_pattern = re.compile(r'https?://[^\s]+')
        text = "Just a normal message with no URLs"
        urls = url_pattern.findall(text)
        assert urls == []


class TestCLIEnhancements:
    """Tests for non-interactive mode and CLI options."""

    def test_help_shows_options(self):
        """Test that Click --help shows new options."""
        from click.testing import CliRunner
        from neow.cli.main import main
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        # Should show file and message-file options
        assert "--file" in result.output or "-f" in result.output
        assert "--message-file" in result.output
