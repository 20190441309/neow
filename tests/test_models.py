"""Tests for AI model clients."""

import pytest
from typing import Any, Dict, List, Optional

from neow.models.base import ModelResponse, BaseModelClient


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
