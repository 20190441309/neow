"""OpenAI model client."""

from typing import Any, Dict, List, Optional

import openai

from neow.models.base import BaseModelClient, ModelResponse
from neow.utils.logger import logger


class OpenAIClient(BaseModelClient):
    """OpenAI model client."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key.
            model: Model name (default: gpt-4o).
        """
        super().__init__(api_key, model)
        self.client = openai.OpenAI(api_key=api_key)

    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ModelResponse:
        """Send chat request to OpenAI.

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
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        # Prepare request kwargs
        kwargs = {
            "model": self.model,
            "messages": full_messages,
        }

        if tools:
            kwargs["tools"] = tools

        try:
            response = self.client.chat.completions.create(**kwargs)  # type: ignore
            choice = response.choices[0]

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

            return ModelResponse(
                content=choice.message.content or "", tool_calls=tool_calls, usage=usage
            )
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    def validate_connection(self) -> bool:
        """Validate connection to OpenAI API.

        Returns:
            True if connection is valid, False otherwise.
        """
        try:
            self.client.models.list()
            return True
        except Exception as e:
            logger.error(f"OpenAI connection validation failed: {e}")
            return False
