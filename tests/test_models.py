"""Tests for AI model clients."""

import pytest
from unittest.mock import patch, MagicMock

from neow.models.base import ModelResponse, BaseModelClient, StreamChunk
from neow.models.deepseek import DeepSeekClient
from neow.models.anthropic import AnthropicClient
from neow.models.openai import OpenAIClient


class TestModelResponse:
    """Tests for ModelResponse class."""

    def test_init_with_content_only(self):
        """Test ModelResponse initialization with content only."""
        response = ModelResponse(content="Hello, world!")
        assert response.content == "Hello, world!"
        assert response.tool_calls == []
        assert response.usage == {}

    def test_init_with_tool_calls(self):
        """Test ModelResponse initialization with tool calls."""
        tool_calls = [{"name": "search", "args": {"query": "test"}}]
        response = ModelResponse(content="", tool_calls=tool_calls)
        assert response.tool_calls == tool_calls

    def test_init_with_usage(self):
        """Test ModelResponse initialization with usage stats."""
        usage = {"prompt_tokens": 10, "completion_tokens": 20}
        response = ModelResponse(content="", usage=usage)
        assert response.usage == usage

    def test_has_tool_calls_true(self):
        """Test has_tool_calls property when tool calls exist."""
        tool_calls = [{"name": "search", "args": {}}]
        response = ModelResponse(content="", tool_calls=tool_calls)
        assert response.has_tool_calls is True

    def test_has_tool_calls_false_empty(self):
        """Test has_tool_calls property when tool_calls is empty."""
        response = ModelResponse(content="test")
        assert response.has_tool_calls is False

    def test_has_tool_calls_false_none(self):
        """Test has_tool_calls property when tool_calls is None."""
        response = ModelResponse(content="test", tool_calls=None)
        assert response.has_tool_calls is False

    def test_tool_calls_default_empty_list(self):
        """Test that tool_calls defaults to empty list, not None."""
        response = ModelResponse(content="test")
        # Should be a list, not None
        assert isinstance(response.tool_calls, list)
        assert len(response.tool_calls) == 0

    def test_usage_default_empty_dict(self):
        """Test that usage defaults to empty dict, not None."""
        response = ModelResponse(content="test")
        # Should be a dict, not None
        assert isinstance(response.usage, dict)
        assert len(response.usage) == 0


class TestBaseModelClient:
    """Tests for BaseModelClient class."""

    def test_cannot_instantiate_abstract(self):
        """Test that BaseModelClient cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseModelClient(api_key="test-key", model="test-model")

    def test_concrete_subclass_init(self):
        """Test that a concrete subclass can be instantiated."""

        class ConcreteClient(BaseModelClient):
            def chat(self, messages, system_prompt=None, tools=None):
                return ModelResponse(content="test")

            def validate_connection(self):
                return True

        client = ConcreteClient(api_key="test-key", model="test-model")
        assert client.api_key == "test-key"
        assert client.model == "test-model"

    def test_concrete_subclass_chat(self):
        """Test that a concrete subclass implements chat."""

        class ConcreteClient(BaseModelClient):
            def chat(self, messages, system_prompt=None, tools=None):
                return ModelResponse(content="response")

            def validate_connection(self):
                return True

        client = ConcreteClient(api_key="test-key", model="test-model")
        messages = [{"role": "user", "content": "Hello"}]
        response = client.chat(messages)
        assert isinstance(response, ModelResponse)
        assert response.content == "response"

    def test_concrete_subclass_validate_connection(self):
        """Test that a concrete subclass implements validate_connection."""

        class ConcreteClient(BaseModelClient):
            def chat(self, messages, system_prompt=None, tools=None):
                return ModelResponse(content="test")

            def validate_connection(self):
                return True

        client = ConcreteClient(api_key="test-key", model="test-model")
        assert client.validate_connection() is True

    def test_incomplete_subclass_raises(self):
        """Test that incomplete subclass raises TypeError."""

        class IncompleteClient(BaseModelClient):
            def chat(self, messages, system_prompt=None, tools=None):
                return ModelResponse(content="test")

            # Missing validate_connection

        with pytest.raises(TypeError):
            IncompleteClient(api_key="test-key", model="test-model")

    def test_incomplete_subclass_missing_chat(self):
        """Test that subclass missing chat raises TypeError."""

        class IncompleteClient(BaseModelClient):
            def validate_connection(self):
                return True

            # Missing chat

        with pytest.raises(TypeError):
            IncompleteClient(api_key="test-key", model="test-model")


class TestDeepSeekClient:
    """Tests for DeepSeekClient."""

    def test_init(self):
        """Test client initialization."""
        client = DeepSeekClient(api_key="sk-test", model="deepseek-chat")
        assert client.api_key == "sk-test"
        assert client.model == "deepseek-chat"

    @patch("neow.models.deepseek.openai.OpenAI")
    def test_chat_without_tools(self, mock_openai):
        """Test chat without tools."""
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.choices[0].message.tool_calls = None
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="sk-test", model="deepseek-chat")
        messages = [{"role": "user", "content": "Hello"}]
        response = client.chat(messages)

        assert isinstance(response, ModelResponse)
        assert response.content == "Hello!"
        assert response.has_tool_calls is False
        assert response.usage["total_tokens"] == 15

    @patch("neow.models.deepseek.openai.OpenAI")
    def test_chat_with_tools(self, mock_openai):
        """Test chat with tools."""
        # Mock OpenAI response with tool call
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "read_file"
        mock_tool_call.function.arguments = '{"file_path": "test.py"}'

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""
        mock_response.choices[0].message.tool_calls = [mock_tool_call]
        mock_response.usage.prompt_tokens = 20
        mock_response.usage.completion_tokens = 10
        mock_response.usage.total_tokens = 30

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="sk-test", model="deepseek-chat")
        messages = [{"role": "user", "content": "Read test.py"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {
                        "type": "object",
                        "properties": {"file_path": {"type": "string"}},
                    },
                },
            }
        ]
        response = client.chat(messages, tools=tools)

        assert response.has_tool_calls is True
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["id"] == "call_123"
        assert response.tool_calls[0]["function"]["name"] == "read_file"

    @patch("neow.models.deepseek.openai.OpenAI")
    def test_validate_connection_success(self, mock_openai):
        """Test successful connection validation."""
        mock_client = MagicMock()
        mock_client.models.list.return_value = []
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="sk-test", model="deepseek-chat")
        assert client.validate_connection() is True

    @patch("neow.models.deepseek.openai.OpenAI")
    def test_validate_connection_failure(self, mock_openai):
        """Test failed connection validation."""
        mock_client = MagicMock()
        mock_client.models.list.side_effect = Exception("Connection failed")
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="sk-test", model="deepseek-chat")
        assert client.validate_connection() is False


class TestAnthropicClient:
    """Tests for AnthropicClient."""

    def test_init(self):
        """Test client initialization."""
        client = AnthropicClient(api_key="sk-ant-test", model="claude-sonnet-4-6")
        assert client.api_key == "sk-ant-test"
        assert client.model == "claude-sonnet-4-6"

    @patch("neow.models.anthropic.anthropic.Anthropic")
    def test_chat_without_tools(self, mock_anthropic):
        """Test chat without tools."""
        # Mock Anthropic response
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "Hello!"
        mock_response.content[0].type = "text"
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = AnthropicClient(api_key="sk-ant-test", model="claude-sonnet-4-6")
        messages = [{"role": "user", "content": "Hello"}]
        response = client.chat(messages)

        assert isinstance(response, ModelResponse)
        assert response.content == "Hello!"
        assert response.has_tool_calls is False
        assert response.usage["total_tokens"] == 15

    @patch("neow.models.anthropic.anthropic.Anthropic")
    def test_chat_with_tools(self, mock_anthropic):
        """Test chat with tools."""
        # Mock Anthropic response with tool use
        mock_tool_use = MagicMock()
        mock_tool_use.type = "tool_use"
        mock_tool_use.id = "toolu_123"
        mock_tool_use.name = "read_file"
        mock_tool_use.input = {"file_path": "test.py"}

        mock_response = MagicMock()
        mock_response.content = [mock_tool_use]
        mock_response.stop_reason = "tool_use"
        mock_response.usage.input_tokens = 20
        mock_response.usage.output_tokens = 10

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = AnthropicClient(api_key="sk-ant-test", model="claude-sonnet-4-6")
        messages = [{"role": "user", "content": "Read test.py"}]
        tools = [
            {
                "name": "read_file",
                "description": "Read a file",
                "input_schema": {
                    "type": "object",
                    "properties": {"file_path": {"type": "string"}},
                },
            }
        ]
        response = client.chat(messages, tools=tools)

        assert response.has_tool_calls is True
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["id"] == "toolu_123"
        assert response.tool_calls[0]["function"]["name"] == "read_file"

    @patch("neow.models.anthropic.anthropic.Anthropic")
    def test_validate_connection_success(self, mock_anthropic):
        """Test successful connection validation."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock()
        mock_anthropic.return_value = mock_client

        client = AnthropicClient(api_key="sk-ant-test", model="claude-sonnet-4-6")
        assert client.validate_connection() is True

    @patch("neow.models.anthropic.anthropic.Anthropic")
    def test_validate_connection_failure(self, mock_anthropic):
        """Test failed connection validation."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("Connection failed")
        mock_anthropic.return_value = mock_client

        client = AnthropicClient(api_key="sk-ant-test", model="claude-sonnet-4-6")
        assert client.validate_connection() is False


class TestOpenAIClient:
    """Tests for OpenAIClient."""

    def test_init(self):
        """Test client initialization."""
        client = OpenAIClient(api_key="sk-test", model="gpt-4o")
        assert client.api_key == "sk-test"
        assert client.model == "gpt-4o"

    @patch("neow.models.openai.openai.OpenAI")
    def test_chat_without_tools(self, mock_openai):
        """Test chat without tools."""
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.choices[0].message.tool_calls = None
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = OpenAIClient(api_key="sk-test", model="gpt-4o")
        messages = [{"role": "user", "content": "Hello"}]
        response = client.chat(messages)

        assert isinstance(response, ModelResponse)
        assert response.content == "Hello!"
        assert response.has_tool_calls is False
        assert response.usage["total_tokens"] == 15

    @patch("neow.models.openai.openai.OpenAI")
    def test_chat_with_tools(self, mock_openai):
        """Test chat with tools."""
        # Mock OpenAI response with tool call
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_456"
        mock_tool_call.function.name = "write_file"
        mock_tool_call.function.arguments = (
            '{"file_path": "test.py", "content": "print(1)"}'
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""
        mock_response.choices[0].message.tool_calls = [mock_tool_call]
        mock_response.usage.prompt_tokens = 20
        mock_response.usage.completion_tokens = 10
        mock_response.usage.total_tokens = 30

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = OpenAIClient(api_key="sk-test", model="gpt-4o")
        messages = [{"role": "user", "content": "Write test.py"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                    },
                },
            }
        ]
        response = client.chat(messages, tools=tools)

        assert response.has_tool_calls is True
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["id"] == "call_456"
        assert response.tool_calls[0]["function"]["name"] == "write_file"

    @patch("neow.models.openai.openai.OpenAI")
    def test_validate_connection_success(self, mock_openai):
        """Test successful connection validation."""
        mock_client = MagicMock()
        mock_client.models.list.return_value = []
        mock_openai.return_value = mock_client

        client = OpenAIClient(api_key="sk-test", model="gpt-4o")
        assert client.validate_connection() is True

    @patch("neow.models.openai.openai.OpenAI")
    def test_validate_connection_failure(self, mock_openai):
        """Test failed connection validation."""
        mock_client = MagicMock()
        mock_client.models.list.side_effect = Exception("Connection failed")
        mock_openai.return_value = mock_client

        client = OpenAIClient(api_key="sk-test", model="gpt-4o")
        assert client.validate_connection() is False


class TestStreamChunk:
    """Tests for StreamChunk dataclass."""

    def test_init_defaults(self):
        """Test StreamChunk default values."""
        chunk = StreamChunk()
        assert chunk.content_delta == ""
        assert chunk.reasoning_delta == ""
        assert chunk.tool_call_delta is None
        assert chunk.finish_reason is None
        assert chunk.usage is None

    def test_init_with_content(self):
        """Test StreamChunk with content."""
        chunk = StreamChunk(content_delta="Hello")
        assert chunk.content_delta == "Hello"

    def test_init_with_tool_calls(self):
        """Test StreamChunk with tool calls."""
        tc = {"tool_calls": [{"id": "1", "function": {"name": "test", "arguments": "{}"}}]}
        chunk = StreamChunk(tool_call_delta=tc, finish_reason="tool_calls")
        assert chunk.tool_call_delta == tc
        assert chunk.finish_reason == "tool_calls"

    def test_init_with_usage(self):
        """Test StreamChunk with usage."""
        usage = {"prompt_tokens": 10, "completion_tokens": 20}
        chunk = StreamChunk(usage=usage)
        assert chunk.usage == usage


class TestBaseModelClientStreaming:
    """Tests for default chat_stream fallback."""

    def test_default_chat_stream_fallback(self):
        """Test that default chat_stream wraps chat() as single chunk."""
        # Create a concrete subclass that doesn't override chat_stream
        class SimpleClient(BaseModelClient):
            def chat(self, messages, system_prompt=None, tools=None):
                return ModelResponse(content="Hello", usage={"total_tokens": 10})
            def validate_connection(self):
                return True

        client = SimpleClient(api_key="sk-test", model="test")
        chunks = list(client.chat_stream([{"role": "user", "content": "Hi"}]))
        assert len(chunks) == 1
        assert chunks[0].content_delta == "Hello"
        assert chunks[0].usage == {"total_tokens": 10}
