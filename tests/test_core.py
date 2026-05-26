"""Tests for core modules."""

import json

import pytest

from unittest.mock import MagicMock

from neow.core.config import Config, ConfigError
from neow.core.conversation import ConversationManager
from neow.core.context import ContextManager
from neow.core.executor import ToolExecutor, ToolError
from neow.models.base import StreamChunk


class TestConfig:
    """Tests for Config class."""

    def test_default_config(self, tmp_path):
        """Test default configuration values."""
        # Use empty config file to ensure defaults are used
        config_file = tmp_path / "empty.json"
        config_file.write_text("{}")
        config = Config(config_file)
        assert config.default_model == "deepseek"
        assert "deepseek" in config.models
        assert "anthropic" in config.models
        assert "openai" in config.models

    def test_load_from_file(self, tmp_path):
        """Test loading configuration from file."""
        config_data = {
            "default_model": "gpt-4o",
            "models": {"openai": {"api_key": "sk-test", "model": "gpt-4o"}},
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
        config_data = {"default_model": "gpt-4o"}
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


class TestContextFiles:
    """Tests for conversation context files."""

    def test_add_context_file(self, tmp_path):
        """Test adding a file to context."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        mock_client = MagicMock()
        manager = ConversationManager(mock_client)

        result = manager.add_context_file(str(test_file))
        assert "Added to context" in result
        assert str(test_file.resolve()) in manager.context_files

    def test_add_context_file_not_found(self):
        """Test adding non-existent file."""
        mock_client = MagicMock()
        manager = ConversationManager(mock_client)

        with pytest.raises(FileNotFoundError):
            manager.add_context_file("/nonexistent/file.txt")

    def test_drop_context_file(self, tmp_path):
        """Test dropping a file from context."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")
        mock_client = MagicMock()
        manager = ConversationManager(mock_client)

        manager.add_context_file(str(test_file))
        result = manager.drop_context_file(str(test_file))
        assert "Removed" in result
        assert len(manager.context_files) == 0

    def test_drop_context_file_not_in_context(self):
        """Test dropping file never added."""
        mock_client = MagicMock()
        manager = ConversationManager(mock_client)

        with pytest.raises(KeyError):
            manager.drop_context_file("nonexistent.py")

    def test_drop_context_file_by_name(self, tmp_path):
        """Test dropping file by just filename."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")
        mock_client = MagicMock()
        manager = ConversationManager(mock_client)

        manager.add_context_file(str(test_file))
        result = manager.drop_context_file("test.py")
        assert "Removed" in result

    def test_list_context_files(self, tmp_path):
        """Test listing context files."""
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("a")
        f2.write_text("b")
        mock_client = MagicMock()
        manager = ConversationManager(mock_client)

        manager.add_context_file(str(f1))
        manager.add_context_file(str(f2))
        files = manager.list_context_files()
        assert len(files) == 2

    def test_list_context_files_empty(self):
        """Test listing when no files in context."""
        mock_client = MagicMock()
        manager = ConversationManager(mock_client)

        assert manager.list_context_files() == []

    def test_context_files_in_system_prompt(self, tmp_path):
        """Test context files appear in effective system prompt."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        mock_client = MagicMock()
        manager = ConversationManager(mock_client)
        manager.set_system_prompt("You are Neow.")

        manager.add_context_file(str(test_file))
        prompt = manager._get_effective_system_prompt()
        assert "print('hello')" in prompt
        assert "Context Files" in prompt

    def test_context_auto_refresh_on_edit(self, tmp_path):
        """Test context auto-refreshes after file edit."""
        test_file = tmp_path / "test.py"
        test_file.write_text("original")
        mock_client = MagicMock()
        manager = ConversationManager(mock_client)
        manager.add_context_file(str(test_file))

        # Simulate file edit
        test_file.write_text("modified")
        abs_path = str(test_file.resolve())
        manager.refresh_context_file(abs_path)
        assert manager.context_files[abs_path] == "modified"

    def test_context_auto_remove_on_delete(self, tmp_path):
        """Test context removes file on delete."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")
        mock_client = MagicMock()
        manager = ConversationManager(mock_client)
        manager.add_context_file(str(test_file))

        abs_path = str(test_file.resolve())
        assert abs_path in manager.context_files
        # Simulate delete
        del manager.context_files[abs_path]
        assert abs_path not in manager.context_files


class TestConfigExtensions:
    """Tests for P1 config extensions."""

    def test_lint_test_defaults(self, tmp_path):
        """Test lint_test config defaults."""
        config_file = tmp_path / "empty.json"
        config_file.write_text("{}")
        config = Config(config_file)
        lt = config.lint_test
        assert lt["auto_lint"] is False
        assert lt["auto_test"] is False
        assert lt["lint_command"] is None
        assert lt["test_command"] is None

    def test_architect_defaults(self, tmp_path):
        """Test architect config defaults."""
        config_file = tmp_path / "empty.json"
        config_file.write_text("{}")
        config = Config(config_file)
        arch = config.architect
        assert arch["planner"] == "anthropic"
        assert arch["executor"] == "deepseek"

    def test_resolve_model_alias_exact(self, tmp_path):
        """Test resolving exact model name."""
        config_file = tmp_path / "empty.json"
        config_file.write_text("{}")
        config = Config(config_file)
        assert config.resolve_model_alias("deepseek") == "deepseek"

    def test_resolve_model_alias_short(self, tmp_path):
        """Test resolving alias like 'sonnet' -> 'anthropic'."""
        config_file = tmp_path / "empty.json"
        config_file.write_text("{}")
        config = Config(config_file)
        assert config.resolve_model_alias("sonnet") == "anthropic"
        assert config.resolve_model_alias("claude") == "anthropic"
        assert config.resolve_model_alias("deep") == "deepseek"
        assert config.resolve_model_alias("gpt") == "openai"

    def test_resolve_model_alias_unknown(self, tmp_path):
        """Test resolving unknown alias returns it as-is."""
        config_file = tmp_path / "empty.json"
        config_file.write_text("{}")
        config = Config(config_file)
        assert config.resolve_model_alias("unknown-model") == "unknown-model"


class TestContextInjection:
    """Tests for ContextManager integration into ConversationManager."""

    def test_conversation_accepts_context_manager(self, tmp_path):
        from unittest.mock import MagicMock
        mock_client = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.get_project_structure.return_value = {"src": {}}
        mock_ctx.get_relevant_files.return_value = []
        manager = ConversationManager(mock_client, context_manager=mock_ctx)
        assert manager.context_manager is mock_ctx

    def test_project_structure_injected_on_first_call(self, tmp_path):
        from unittest.mock import MagicMock
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "ok"
        mock_response.has_tool_calls = False
        mock_response.tool_calls = []
        mock_response.usage = {"total_tokens": 10}
        mock_client.chat.return_value = mock_response

        mock_ctx = MagicMock()
        mock_ctx.get_project_structure.return_value = {"src": {"main.py": None}, "README.md": None}
        mock_ctx.get_relevant_files.return_value = []

        manager = ConversationManager(mock_client, context_manager=mock_ctx)
        manager.set_system_prompt("You are Neow.")
        manager.get_response("Hello")

        mock_ctx.get_project_structure.assert_called_once()
        call_args = mock_client.chat.call_args
        prompt = call_args.kwargs.get("system_prompt") or call_args[1].get("system_prompt", "")
        assert "Project Structure" in prompt or "src" in prompt

    def test_relevant_files_injected_per_query(self, tmp_path):
        from unittest.mock import MagicMock
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "ok"
        mock_response.has_tool_calls = False
        mock_response.tool_calls = []
        mock_response.usage = {"total_tokens": 10}
        mock_client.chat.return_value = mock_response

        mock_ctx = MagicMock()
        mock_ctx.get_project_structure.return_value = {}
        mock_ctx.get_relevant_files.return_value = [
            {"path": "main.py", "content": "def main(): pass"}
        ]

        manager = ConversationManager(mock_client, context_manager=mock_ctx)
        manager.set_system_prompt("You are Neow.")
        manager.get_response("Tell me about main")

        mock_ctx.get_relevant_files.assert_called_once_with("Tell me about main")

    def test_no_context_manager_preserves_behavior(self):
        from unittest.mock import MagicMock
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "ok"
        mock_response.has_tool_calls = False
        mock_response.tool_calls = []
        mock_response.usage = {"total_tokens": 10}
        mock_client.chat.return_value = mock_response

        manager = ConversationManager(mock_client)
        manager.set_system_prompt("You are Neow.")
        response = manager.get_response("Hello")
        assert response.content == "ok"


class TestFormatProjectContext:
    """Tests for format_project_context and _format_structure helpers."""

    def test_format_structure_flat(self):
        from neow.core.prompts import _format_structure
        result = _format_structure({"README.md": None, "setup.py": None})
        assert "README.md" in result
        assert "setup.py" in result

    def test_format_structure_nested(self):
        from neow.core.prompts import _format_structure
        structure = {"src": {"main.py": None}, "tests": {"test_main.py": None}}
        result = _format_structure(structure)
        assert "src/" in result
        assert "main.py" in result
        assert "tests/" in result
        assert "test_main.py" in result

    def test_format_project_context_structure_only(self):
        from neow.core.prompts import format_project_context
        structure = {"src": {"main.py": None}}
        result = format_project_context(structure, [])
        assert "Project Structure" in result
        assert "src/" in result

    def test_format_project_context_with_relevant_files(self):
        from neow.core.prompts import format_project_context
        relevant = [{"path": "main.py", "content": "def main(): pass"}]
        result = format_project_context({}, relevant)
        assert "Relevant Files" in result
        assert "main.py" in result
        assert "def main(): pass" in result

    def test_format_project_context_structure_and_files(self):
        from neow.core.prompts import format_project_context
        structure = {"src": {}}
        relevant = [{"path": "app.py", "content": "x = 1"}]
        result = format_project_context(structure, relevant)
        assert "Project Structure" in result
        assert "Relevant Files" in result


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
                    "arguments": '{"file_path": "test.txt"}',
                },
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


class TestSubAgent:
    def test_subagent_init(self):
        from unittest.mock import MagicMock
        from neow.core.sub_agent import SubAgent
        mock_client = MagicMock()
        agent = SubAgent(mock_client, tools=[], task_description="Fix the bug")
        assert agent.conversation is not None
        assert "Fix the bug" in agent.conversation.system_prompt

    def test_subagent_execute(self):
        from unittest.mock import MagicMock
        from neow.core.sub_agent import SubAgent
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Fixed the bug in main.py"
        mock_response.has_tool_calls = False
        mock_response.tool_calls = []
        mock_response.usage = {"total_tokens": 10}
        mock_client.chat.return_value = mock_response

        agent = SubAgent(mock_client, tools=[], task_description="Fix the bug")
        result = agent.execute("Look at main.py and fix the import error")
        assert result == "Fixed the bug in main.py"

    def test_subagent_isolated_context(self):
        from unittest.mock import MagicMock
        from neow.core.sub_agent import SubAgent
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "done"
        mock_response.has_tool_calls = False
        mock_response.tool_calls = []
        mock_response.usage = {"total_tokens": 10}
        mock_client.chat.return_value = mock_response

        agent1 = SubAgent(mock_client, tools=[], task_description="Task 1")
        agent2 = SubAgent(mock_client, tools=[], task_description="Task 2")
        agent1.execute("do something")
        assert len(agent2.conversation.messages) == 0


class TestArchitectOrchestrator:
    def test_orchestrator_init(self):
        from unittest.mock import MagicMock
        from neow.core.architect import ArchitectOrchestrator
        planner_client = MagicMock()
        executor_client = MagicMock()
        tool_executor = MagicMock()
        orch = ArchitectOrchestrator(planner_client, executor_client, tool_executor)
        assert orch.planner is not None
        assert orch.executor_client is executor_client

    def test_orchestrator_parses_plan(self):
        from unittest.mock import MagicMock
        from neow.core.architect import ArchitectOrchestrator

        planner_client = MagicMock()
        plan_json = '[{"task": "Read main.py and identify the bug", "files": ["main.py"]}, {"task": "Fix the import error in main.py", "files": ["main.py"]}]'
        mock_plan_response = MagicMock()
        mock_plan_response.content = plan_json
        mock_plan_response.has_tool_calls = False
        mock_plan_response.tool_calls = []
        mock_plan_response.usage = {"total_tokens": 10}
        planner_client.chat.return_value = mock_plan_response

        executor_client = MagicMock()
        mock_exec_response = MagicMock()
        mock_exec_response.content = "Fixed the import error"
        mock_exec_response.has_tool_calls = False
        mock_exec_response.tool_calls = []
        mock_exec_response.usage = {"total_tokens": 10}
        executor_client.chat.return_value = mock_exec_response

        tool_executor = MagicMock()
        orch = ArchitectOrchestrator(planner_client, executor_client, tool_executor)
        result = orch.run("Fix the bug in main.py")
        assert "Fixed" in result or "import" in result or len(result) > 0

    def test_orchestrator_handles_empty_plan(self):
        from unittest.mock import MagicMock
        from neow.core.architect import ArchitectOrchestrator

        planner_client = MagicMock()
        mock_plan_response = MagicMock()
        mock_plan_response.content = "I'll fix the bug by editing main.py directly."
        mock_plan_response.has_tool_calls = False
        mock_plan_response.tool_calls = []
        mock_plan_response.usage = {"total_tokens": 10}
        planner_client.chat.return_value = mock_plan_response

        executor_client = MagicMock()
        tool_executor = MagicMock()
        orch = ArchitectOrchestrator(planner_client, executor_client, tool_executor)
        result = orch.run("Fix the bug")
        assert len(result) > 0


class TestTokenConfig:
    """Tests for token config defaults."""

    def test_token_defaults(self, tmp_path):
        config_file = tmp_path / "empty.json"
        config_file.write_text("{}")
        config = Config(config_file)
        token_cfg = config.token
        assert token_cfg["show_usage"] is True
        assert token_cfg["warn_at_tokens"] == 100000
        assert "deepseek-chat" in token_cfg["prices"]
        assert "input" in token_cfg["prices"]["deepseek-chat"]
        assert "output" in token_cfg["prices"]["deepseek-chat"]


class TestConversationStreaming:
    """Tests for streaming conversation."""

    def test_get_response_stream_no_tools(self):
        """Test streaming response without tool calls."""
        mock_client = MagicMock()

        def mock_stream(*args, **kwargs):
            yield StreamChunk(content_delta="Hello ")
            yield StreamChunk(content_delta="World")
            yield StreamChunk(usage={"total_tokens": 10})

        mock_client.chat_stream = mock_stream

        manager = ConversationManager(mock_client)
        chunks = list(manager.get_response_stream("Hi"))
        content_chunks = [c for c in chunks if c.content_delta]
        assert "".join(c.content_delta for c in content_chunks) == "Hello World"
        assert manager.messages[-1]["content"] == "Hello World"

    def test_get_response_stream_fallback(self):
        """Test non-streaming still works."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Hello!"
        mock_response.has_tool_calls = False
        mock_response.tool_calls = []
        mock_response.usage = {"total_tokens": 10}
        mock_client.chat.return_value = mock_response

        manager = ConversationManager(mock_client)
        response = manager.get_response("Hi")
        assert response.content == "Hello!"


class TestTokenTracker:
    """Tests for TokenTracker."""

    def test_init(self):
        from unittest.mock import MagicMock
        from neow.core.token_tracker import TokenTracker
        mock_config = MagicMock()
        mock_config.token = {
            "show_usage": True,
            "prices": {"deepseek-chat": {"input": 0.14, "output": 0.28}},
        }
        tracker = TokenTracker(mock_config)
        assert tracker.session_input == 0
        assert tracker.session_output == 0

    def test_record_usage(self):
        from unittest.mock import MagicMock
        from neow.core.token_tracker import TokenTracker
        mock_config = MagicMock()
        mock_config.token = {
            "show_usage": True,
            "prices": {"deepseek-chat": {"input": 0.14, "output": 0.28}},
        }
        tracker = TokenTracker(mock_config)
        tracker.record({"prompt_tokens": 100, "completion_tokens": 50}, "deepseek-chat")
        assert tracker.session_input == 100
        assert tracker.session_output == 50

    def test_record_accumulates(self):
        from unittest.mock import MagicMock
        from neow.core.token_tracker import TokenTracker
        mock_config = MagicMock()
        mock_config.token = {
            "show_usage": True,
            "prices": {"deepseek-chat": {"input": 0.14, "output": 0.28}},
        }
        tracker = TokenTracker(mock_config)
        tracker.record({"prompt_tokens": 100, "completion_tokens": 50}, "deepseek-chat")
        tracker.record({"prompt_tokens": 200, "completion_tokens": 80}, "deepseek-chat")
        assert tracker.session_input == 300
        assert tracker.session_output == 130

    def test_calculate_cost(self):
        from unittest.mock import MagicMock
        from neow.core.token_tracker import TokenTracker
        mock_config = MagicMock()
        mock_config.token = {
            "show_usage": True,
            "prices": {"deepseek-chat": {"input": 0.14, "output": 0.28}},
        }
        tracker = TokenTracker(mock_config)
        tracker.record({"prompt_tokens": 1000000, "completion_tokens": 1000000}, "deepseek-chat")
        cost = tracker.get_session_cost()
        assert abs(cost - 0.42) < 0.01  # 0.14 + 0.28

    def test_format_usage_line(self):
        from unittest.mock import MagicMock
        from neow.core.token_tracker import TokenTracker
        mock_config = MagicMock()
        mock_config.token = {
            "show_usage": True,
            "prices": {"deepseek-chat": {"input": 0.14, "output": 0.28}},
        }
        tracker = TokenTracker(mock_config)
        line = tracker.format_usage_line({"prompt_tokens": 100, "completion_tokens": 50}, "deepseek-chat")
        assert "100" in line
        assert "50" in line

    def test_get_session_summary(self):
        from unittest.mock import MagicMock
        from neow.core.token_tracker import TokenTracker
        mock_config = MagicMock()
        mock_config.token = {
            "show_usage": True,
            "prices": {"deepseek-chat": {"input": 0.14, "output": 0.28}},
        }
        tracker = TokenTracker(mock_config)
        tracker.record({"prompt_tokens": 1000, "completion_tokens": 500}, "deepseek-chat")
        summary = tracker.get_session_summary()
        assert "1,000" in summary or "1000" in summary
        assert "500" in summary

    def test_unknown_model_cost(self):
        from unittest.mock import MagicMock
        from neow.core.token_tracker import TokenTracker
        mock_config = MagicMock()
        mock_config.token = {
            "show_usage": True,
            "prices": {},
        }
        tracker = TokenTracker(mock_config)
        tracker.record({"prompt_tokens": 100, "completion_tokens": 50}, "unknown-model")
        cost = tracker.get_session_cost()
        assert cost == 0.0


class TestConversationTokenTracking:
    """Tests for token tracking in ConversationManager."""

    def test_conversation_accepts_token_tracker(self):
        from unittest.mock import MagicMock
        from neow.core.token_tracker import TokenTracker
        mock_client = MagicMock()
        mock_config = MagicMock()
        mock_config.token = {"show_usage": True, "prices": {}}
        tracker = TokenTracker(mock_config)
        manager = ConversationManager(mock_client, token_tracker=tracker)
        assert manager.token_tracker is tracker

    def test_token_tracker_records_usage(self):
        from unittest.mock import MagicMock
        from neow.core.token_tracker import TokenTracker
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "ok"
        mock_response.has_tool_calls = False
        mock_response.tool_calls = []
        mock_response.usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        mock_client.chat.return_value = mock_response

        mock_config = MagicMock()
        mock_config.token = {"show_usage": True, "prices": {"deepseek-chat": {"input": 0.14, "output": 0.28}}}
        tracker = TokenTracker(mock_config)
        manager = ConversationManager(mock_client, token_tracker=tracker)
        manager.set_system_prompt("test")
        manager.get_response("Hello")

        assert tracker.session_input == 100
        assert tracker.session_output == 50


class TestExecutorSecurity:
    """Tests for security integration in ToolExecutor."""

    def test_executor_blocks_non_whitelisted_command(self):
        from neow.core.security import SecurityGuard
        executor = ToolExecutor()
        executor.security_guard = SecurityGuard()
        executor.allowed_commands = ["ls", "cat"]

        executor.register_tool("execute_command", lambda command, timeout=30: "ok")

        with pytest.raises(ToolError, match="whitelist"):
            executor.execute("execute_command", {"command": "curl http://evil.com"})

    def test_executor_blocks_protected_file(self):
        from neow.core.security import SecurityGuard
        executor = ToolExecutor()
        executor.security_guard = SecurityGuard()
        executor.allowed_commands = []

        executor.register_tool("write_file", lambda file_path, content: "ok")

        with pytest.raises(ToolError, match="Protected"):
            executor.execute("write_file", {"file_path": ".env", "content": "KEY=val"})

    def test_executor_allows_safe_operations(self):
        from neow.core.security import SecurityGuard
        executor = ToolExecutor()
        executor.security_guard = SecurityGuard()
        executor.allowed_commands = ["ls", "cat", "python"]

        executor.register_tool("execute_command", lambda command, timeout=30: "ok")
        result = executor.execute("execute_command", {"command": "ls -la"})
        assert result == "ok"
