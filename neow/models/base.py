"""Base class for AI model clients."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional


class ModelResponse:
    """Response from AI model."""

    def __init__(
        self,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        usage: Optional[Dict[str, int]] = None,
    ):
        """Initialize model response.

        Args:
            content: Response content.
            tool_calls: List of tool calls requested by the model.
            usage: Token usage statistics.
        """
        self.content = content
        self.tool_calls = tool_calls or []
        self.usage = usage or {}

    @property
    def has_tool_calls(self) -> bool:
        """Check if response has tool calls."""
        return len(self.tool_calls) > 0


@dataclass
class StreamChunk:
    """A single chunk from a streaming response."""

    content_delta: str = ""
    reasoning_delta: str = ""
    tool_call_delta: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None


class BaseModelClient(ABC):
    """Base class for AI model clients."""

    def __init__(self, api_key: str, model: str):
        """Initialize model client.

        Args:
            api_key: API key for the model service.
            model: Model name/identifier.
        """
        self.api_key = api_key
        self.model = model

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ModelResponse:
        """Send chat request to AI model.

        Args:
            messages: List of message dictionaries with 'role' and 'content'.
            system_prompt: Optional system prompt.
            tools: Optional list of tool definitions.

        Returns:
            ModelResponse object.
        """
        pass

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Generator[StreamChunk, None, None]:
        """Send streaming chat request. Default: wraps chat() as single chunk.

        Args:
            messages: List of message dictionaries.
            system_prompt: Optional system prompt.
            tools: Optional list of tool definitions.

        Yields:
            StreamChunk objects.
        """
        response = self.chat(messages, system_prompt, tools)
        yield StreamChunk(content_delta=response.content, usage=response.usage)

    @abstractmethod
    def validate_connection(self) -> bool:
        """Validate connection to AI model service.

        Returns:
            True if connection is valid, False otherwise.
        """
        pass
