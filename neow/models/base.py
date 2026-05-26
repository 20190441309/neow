"""Base class for AI model clients."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ModelResponse:
    """Response from AI model."""

    def __init__(
        self,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        usage: Optional[Dict[str, int]] = None
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
        tools: Optional[List[Dict[str, Any]]] = None
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

    @abstractmethod
    def validate_connection(self) -> bool:
        """Validate connection to AI model service.

        Returns:
            True if connection is valid, False otherwise.
        """
        pass
