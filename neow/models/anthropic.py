"""Anthropic Claude model client."""

import json
from typing import Any, Dict, Generator, List, Optional

import anthropic

from neow.models.adapters import to_anthropic
from neow.models.base import BaseModelClient, ModelResponse, StreamChunk
from neow.utils import sanitize_text as _sanitize_text
from neow.utils.logger import logger


class AnthropicClient(BaseModelClient):
    """Anthropic Claude model client."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        base_url: Optional[str] = None,
        validate: bool = True,
    ):
        """Initialize Anthropic client.

        Args:
            api_key: Anthropic API key.
            model: Model name (default: claude-sonnet-4-6).
            base_url: Optional custom endpoint.
            validate: Whether to run the startup connection probe.
        """
        super().__init__(api_key, model)
        self.base_url = base_url
        self.validate_enabled = validate
        kwargs: Dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = anthropic.Anthropic(**kwargs)

    def _request_kwargs(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str],
        tools: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Messages API kwargs; converts neow's OpenAI-style history."""
        api_messages, api_tools = to_anthropic(messages, tools)
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": api_messages,
        }
        if system_prompt:
            kwargs["system"] = _sanitize_text(system_prompt)
        if api_tools:
            kwargs["tools"] = api_tools
        return kwargs

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

        kwargs = self._request_kwargs(sanitized_messages, system_prompt, tools)

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

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Generator[StreamChunk, None, None]:
        """Send streaming chat request to Anthropic.

        Args:
            messages: List of message dictionaries.
            system_prompt: Optional system prompt.
            tools: Optional list of tool definitions.

        Yields:
            StreamChunk objects.
        """
        sanitized_messages = []
        for msg in messages:
            sanitized_msg = {k: _sanitize_text(v) if isinstance(v, str) else v for k, v in msg.items()}
            sanitized_messages.append(sanitized_msg)

        kwargs = self._request_kwargs(sanitized_messages, system_prompt, tools)

        try:
            # Content block index -> tool_use being assembled.  Argument
            # deltas name their block by index, so parallel calls stay apart.
            tool_inputs: Dict[int, Dict[str, str]] = {}

            with self.client.messages.stream(**kwargs) as stream:
                for event in stream:
                    if event.type == "content_block_start":
                        if event.content_block.type == "tool_use":
                            tool_inputs[event.index] = {
                                "id": event.content_block.id,
                                "name": event.content_block.name,
                                "input_buffer": "",
                            }
                    elif event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            yield StreamChunk(content_delta=event.delta.text)
                        elif event.delta.type == "input_json_delta":
                            if event.index in tool_inputs:
                                tool_inputs[event.index]["input_buffer"] += (
                                    event.delta.partial_json
                                )
                    elif event.type == "message_stop":
                        final_tool_calls = []
                        for index in sorted(tool_inputs):
                            tinfo = tool_inputs[index]
                            final_tool_calls.append({
                                "id": tinfo["id"],
                                "function": {
                                    "name": tinfo["name"],
                                    # Tools without arguments stream no deltas.
                                    "arguments": tinfo["input_buffer"] or "{}",
                                },
                            })
                        yield StreamChunk(
                            finish_reason="tool_use" if final_tool_calls else "end_turn",
                            tool_call_delta={"tool_calls": final_tool_calls} if final_tool_calls else None,
                        )

                final_message = stream.get_final_message()
                if final_message and final_message.usage:
                    yield StreamChunk(
                        usage={
                            "prompt_tokens": final_message.usage.input_tokens,
                            "completion_tokens": final_message.usage.output_tokens,
                            "total_tokens": final_message.usage.input_tokens + final_message.usage.output_tokens,
                        }
                    )

        except Exception as e:
            logger.error(f"Anthropic streaming error: {e}")
            raise

    def validate_connection(self) -> bool:
        """Validate connection to Anthropic API.

        Returns:
            True if connection is valid, False otherwise.
        """
        if not self.validate_enabled:
            return True
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
