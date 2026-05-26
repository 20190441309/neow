"""Tests for core modules."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from neow.core.config import Config, ConfigError
from neow.core.conversation import ConversationManager
from neow.core.context import ContextManager
from neow.core.executor import ToolExecutor, ToolError
from neow.tools.file_ops import read_file, write_file


class TestConfig:
    """Tests for Config class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = Config()
        assert config.default_model == "deepseek-chat"
        assert "deepseek" in config.models
        assert "anthropic" in config.models
        assert "openai" in config.models

    def test_load_from_file(self, tmp_path):
        """Test loading configuration from file."""
        config_data = {
            "default_model": "gpt-4o",
            "models": {
                "openai": {
                    "api_key": "sk-test",
                    "model": "gpt-4o"
                }
            }
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        config = Config(config_file)
        assert config.default_model == "gpt-4o"
        assert config.models["openai"]["api_key"] == "sk-test"

    def test_load_from_env(self, monkeypatch):
        """Test loading API keys from environment variables."""
        monkeypatch.setenv("NEOW_DEEPSEEK_API_KEY", "sk-env-test")
        config = Config()
        assert config.models["deepseek"]["api_key"] == "sk-env-test"

    def test_invalid_config_file(self, tmp_path):
        """Test handling of invalid config file."""
        config_file = tmp_path / "invalid.json"
        config_file.write_text("invalid json")

        with pytest.raises(ConfigError):
            Config(config_file)

    def test_merge_configs(self, tmp_path):
        """Test merging file config with defaults."""
        config_data = {
            "default_model": "gpt-4o"
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        config = Config(config_file)
        assert config.default_model == "gpt-4o"
        # Should still have default models
        assert "deepseek" in config.models


class TestToolExecutor:
    """Tests for ToolExecutor."""

    def test_init(self):
        """Test executor initialization."""
        executor = ToolExecutor()
        assert "read_file" in executor.tools
        assert "write_file" in executor.tools
        assert "edit_file" in executor.tools
        assert "execute_command" in executor.tools
        assert "search_code" in executor.tools

    def test_execute_unknown_tool(self):
        """Test executing unknown tool."""
        executor = ToolExecutor()
        with pytest.raises(ToolError):
            executor.execute("unknown_tool", {})

    def test_register_custom_tool(self):
        """Test registering custom tool."""
        executor = ToolExecutor()

        def custom_tool(param: str) -> str:
            return f"Custom: {param}"

        executor.register_tool("custom", custom_tool)
        assert "custom" in executor.tools

        result = executor.execute("custom", {"param": "test"})
        assert result == "Custom: test"


class TestConversationManager:
    """Tests for ConversationManager."""

    def test_init(self):
        """Test conversation manager initialization."""
        mock_client = MagicMock()
        manager = ConversationManager(mock_client)
        assert len(manager.messages) == 0
        assert manager.system_prompt == ""

    def test_add_message(self):
        """Test adding messages."""
        mock_client = MagicMock()
        manager = ConversationManager(mock_client)

        manager.add_message("user", "Hello")
        assert len(manager.messages) == 1
        assert manager.messages[0]["role"] == "user"
        assert manager.messages[0]["content"] == "Hello"

    def test_clear_history(self):
        """Test clearing history."""
        mock_client = MagicMock()
        manager = ConversationManager(mock_client)

        manager.add_message("user", "Hello")
        manager.add_message("assistant", "Hi")
        manager.clear_history()
        assert len(manager.messages) == 0

    def test_get_response(self):
        """Test getting response."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Hello!"
        mock_response.has_tool_calls = False
        mock_response.tool_calls = []
        mock_response.usage = {"total_tokens": 10}
        mock_client.chat.return_value = mock_response

        manager = ConversationManager(mock_client)
        response = manager.get_response("Hello")

        assert response.content == "Hello!"
        assert len(manager.messages) == 2  # user + assistant


class TestContextManager:
    """Tests for ContextManager."""

    def test_init(self, tmp_path):
        """Test context manager initialization."""
        manager = ContextManager(str(tmp_path))
        assert manager.project_root == tmp_path

    def test_get_project_structure(self, tmp_path):
        """Test getting project structure."""
        # Create test structure
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hello')")
        (tmp_path / "README.md").write_text("# Test")

        manager = ContextManager(str(tmp_path))
        structure = manager.get_project_structure()

        assert "src" in structure
        assert "README.md" in structure

    def test_get_relevant_files(self, tmp_path):
        """Test getting relevant files."""
        # Create test files
        (tmp_path / "main.py").write_text("def main(): pass")
        (tmp_path / "utils.py").write_text("def helper(): pass")
        (tmp_path / "README.md").write_text("# Documentation")

        manager = ContextManager(str(tmp_path))
        files = manager.get_relevant_files("main function")

        assert len(files) > 0

    def test_build_context(self, tmp_path):
        """Test building context."""
        # Create test file
        (tmp_path / "test.py").write_text("def hello(): pass")

        manager = ContextManager(str(tmp_path))
        context = manager.build_context("tell me about test.py")

        assert "test.py" in context


class TestIntegration:
    """Integration tests."""

    def test_conversation_with_tools(self):
        """Test conversation with tool execution."""
        # Mock model client
        mock_client = MagicMock()

        # First response: tool call
        mock_response1 = MagicMock()
        mock_response1.content = ""
        mock_response1.has_tool_calls = True
        mock_response1.tool_calls = [
            {
                "id": "call_1",
                "function": {
                    "name": "read_file",
                    "arguments": '{"file_path": "test.txt"}'
                }
            }
        ]
        mock_response1.usage = {"total_tokens": 10}

        # Second response: final answer
        mock_response2 = MagicMock()
        mock_response2.content = "The file contains: Hello"
        mock_response2.has_tool_calls = False
        mock_response2.tool_calls = []
        mock_response2.usage = {"total_tokens": 20}

        mock_client.chat.side_effect = [mock_response1, mock_response2]

        # Create conversation manager with mock tool executor
        mock_executor = MagicMock()
        mock_executor.execute.return_value = "Hello"
        conversation = ConversationManager(mock_client, tool_executor=mock_executor)

        # Get response
        response = conversation.get_response("Read test.txt")

        # Verify
        assert response.content == "The file contains: Hello"
        assert mock_client.chat.call_count == 2
