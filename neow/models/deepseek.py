"""DeepSeek model client."""

from typing import Any, Dict, List, Optional

import openai

from neow.models.base import BaseModelClient, ModelResponse
from neow.utils.logger import logger


def _sanitize_text(text: str) -> str:
    """Remove surrogate characters that cause encoding errors."""
    return text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")


class DeepSeekClient(BaseModelClient):
    """DeepSeek model client using OpenAI-compatible API."""

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        """Initialize DeepSeek client.

        Args:
            api_key: DeepSeek API key.
            model: Model name (default: deepseek-chat).
        """
        super().__init__(api_key, model)
        self.client = openai.OpenAI(
            api_key=api_key, base_url="https://api.deepseek.com"
        )
        self._last_reasoning_content = None

    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ModelResponse:
        """Send chat request to DeepSeek.

        Args:
            messages: List of message dictionaries.
            system_prompt: Optional system prompt.
            tools: Optional list of tool definitions.

        Returns:
            ModelResponse object.
        """
        # Prepare messages
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": _sanitize_text(system_prompt)})
        for msg in messages:
            sanitized_msg = {k: _sanitize_text(v) if isinstance(v, str) else v for k, v in msg.items()}
            full_messages.append(sanitized_msg)

        # Prepare request kwargs
        kwargs = {
            "model": self.model,
            "messages": full_messages,
        }

        if tools:
            kwargs["tools"] = tools

        try:
            logger.debug(f"Sending request to DeepSeek API with {len(full_messages)} messages")
            response = self.client.chat.completions.create(**kwargs)  # type: ignore
            choice = response.choices[0]
            logger.debug(f"Received response from DeepSeek API")

            # Parse tool calls
            tool_calls = []
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_calls.append(
                        {
                            "id": tc.id,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                    )

            # Parse usage
            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            # Store reasoning_content for next request if present
            if hasattr(choice.message, 'reasoning_content') and choice.message.reasoning_content:
                self._last_reasoning_content = choice.message.reasoning_content
                logger.debug(f"Stored reasoning_content: {len(choice.message.reasoning_content)} chars")
            else:
                self._last_reasoning_content = None
                logger.debug("No reasoning_content in response")

            return ModelResponse(
                content=choice.message.content or "", tool_calls=tool_calls, usage=usage
            )
        except Exception as e:
            logger.error(f"DeepSeek API error: {e}")
            raise

    def validate_connection(self) -> bool:
        """Validate connection to DeepSeek API.

        Returns:
            True if connection is valid, False otherwise.
        """
        try:
            self.client.models.list()
            return True
        except Exception as e:
            logger.error(f"DeepSeek connection validation failed: {e}")
            return False
