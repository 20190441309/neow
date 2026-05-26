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
