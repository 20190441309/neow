"""Anthropic Claude model client."""

import json
from typing import Any, Dict, List, Optional

import anthropic

from neow.models.base import BaseModelClient, ModelResponse
from neow.utils.logger import logger


def _sanitize_text(text: str) -> str:
    """Remove surrogate characters that cause encoding errors."""
    return text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")


class AnthropicClient(BaseModelClient):
    """Anthropic Claude model client."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        """Initialize Anthropic client.

        Args:
            api_key: Anthropic API key.
            model: Model name (default: claude-sonnet-4-6).
        """
        super().__init__(api_key, model)
        self.client = anthropic.Anthropic(api_key=api_key)

    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ModelResponse:
        """Send chat request to Anthropic Claude.

        Args:
            messages: List of message dictionaries.
            system_prompt: Optional system prompt.
            tools: Optional list of tool definitions.

        Returns:
            ModelResponse object.
        """
        # Sanitize messages to remove surrogate characters
        sanitized_messages = []
        for msg in messages:
            sanitized_msg = {k: _sanitize_text(v) if isinstance(v, str) else v for k, v in msg.items()}
            sanitized_messages.append(sanitized_msg)

        # Prepare request kwargs
        kwargs = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": sanitized_messages,
        }

        if system_prompt:
            kwargs["system"] = _sanitize_text(system_prompt)

        if tools:
            kwargs["tools"] = tools

        try:
            response = self.client.messages.create(  # type: ignore[call-overload]
                **kwargs
            )

            # Parse content
            content = ""
            tool_calls = []

            for block in response.content:
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    tool_calls.append(
                        {
                            "id": block.id,
                            "function": {
                                "name": block.name,
                                "arguments": json.dumps(block.input),
                            },
                        }
                    )

            # Parse usage
            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens
                    + response.usage.output_tokens,
                }

            return ModelResponse(content=content, tool_calls=tool_calls, usage=usage)
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise

    def validate_connection(self) -> bool:
        """Validate connection to Anthropic API.

        Returns:
            True if connection is valid, False otherwise.
        """
        try:
            self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}],
            )
            return True
        except Exception as e:
            logger.error(f"Anthropic connection validation failed: {e}")
            return False
