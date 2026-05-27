"""OpenAI model client."""

from typing import Any, Dict, Generator, List, Optional

import openai

from neow.models.base import BaseModelClient, ModelResponse, StreamChunk
from neow.utils.logger import logger


def _sanitize_text(text: str) -> str:
    """Remove surrogate characters that cause encoding errors."""
    return text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")


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

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Generator[StreamChunk, None, None]:
        """Send streaming chat request to OpenAI.

        Args:
            messages: List of message dictionaries.
            system_prompt: Optional system prompt.
            tools: Optional list of tool definitions.

        Yields:
            StreamChunk objects.
        """
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": _sanitize_text(system_prompt)})
        for msg in messages:
            sanitized_msg = {k: _sanitize_text(v) if isinstance(v, str) else v for k, v in msg.items()}
            full_messages.append(sanitized_msg)

        kwargs = {"model": self.model, "messages": full_messages, "stream": True}
        if tools:
            kwargs["tools"] = tools

        try:
            response = self.client.chat.completions.create(**kwargs)
            tool_calls_acc: Dict[int, Dict] = {}

            for chunk in response:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta

                if delta.content:
                    yield StreamChunk(content_delta=delta.content)

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc_delta.id:
                            tool_calls_acc[idx]["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_calls_acc[idx]["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_calls_acc[idx]["arguments"] += tc_delta.function.arguments

                if choice.finish_reason:
                    final_tool_calls = []
                    for idx in sorted(tool_calls_acc.keys()):
                        tc = tool_calls_acc[idx]
                        final_tool_calls.append({
                            "id": tc["id"],
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        })
                    yield StreamChunk(
                        finish_reason=choice.finish_reason,
                        tool_call_delta={"tool_calls": final_tool_calls} if final_tool_calls else None,
                    )

        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")
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
