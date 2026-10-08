"""Base class for AI model clients."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Generator, List, Optional

from neow.utils.logger import logger


def validate_openai_compatible(client: Any, label: str) -> bool:
    """Validate an OpenAI-compatible endpoint, tolerating a missing /models."""

    try:
        client.models.list()
        return True
    except Exception as exc:  # noqa: BLE001 - reported through the return value
        status = getattr(exc, "status_code", None)
        if status in (404, 405, 501):
            logger.debug(
                f"{label}: endpoint has no /models (HTTP {status}); assuming compatible"
            )
            return True
        logger.error(f"{label} connection validation failed: {exc}")
        return False


# Provider stop reasons -> "stop" | "tool_calls" | "length".
_FINISH_REASONS = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
}


def normalize_finish_reason(reason: Any) -> Optional[str]:
    """Map a provider stop reason onto OpenAI's vocabulary."""

    if not isinstance(reason, str) or not reason:
        return None
    return _FINISH_REASONS.get(reason, reason)


class ModelResponse:
    """Response from AI model."""

    def __init__(
        self,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        usage: Optional[Dict[str, int]] = None,
        finish_reason: Optional[str] = None,
    ):
        """Initialize model response.

        Args:
            content: Response content.
            tool_calls: List of tool calls requested by the model.
            usage: Token usage statistics.
            finish_reason: Normalised stop reason ("stop", "tool_calls",
                "length"), when the provider reports one.
        """
        self.content = content
        self.tool_calls = tool_calls or []
        self.usage = usage or {}
        self.finish_reason = finish_reason

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
    progress: Optional[Dict[str, Any]] = None
    """Progress notification during streaming.
    Set when this chunk represents a progress update (not model output).
    Types: 'tool_start', 'tool_end', 'reasoning_start', 'reasoning_end'.
    """


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
        self.base_url: Optional[str] = None
        self.validate_enabled: bool = True
        # Output token cap sent with each request (None = provider default).
        self.max_output_tokens: Optional[int] = None

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
