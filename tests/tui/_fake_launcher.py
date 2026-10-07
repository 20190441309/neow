"""Launch neow with a fake model client over a real terminal (PTY smoke).

Usage: ``python -m tests.tui._fake_launcher [--plain | --tui | "prompt"]``
"""

import sys
from unittest.mock import patch

from neow.cli import main as main_mod
from neow.models.base import ModelResponse, StreamChunk


class FakeClient:
    """Offline model client: no network, deterministic output."""

    model = "fake"

    def __init__(self, *args, **kwargs):
        pass

    def validate_connection(self) -> bool:
        return True

    def chat(self, messages, system_prompt=None, tools=None) -> ModelResponse:
        return ModelResponse(
            content="fake response",
            usage={"prompt_tokens": 1, "completion_tokens": 2},
        )

    def chat_stream(self, messages, system_prompt=None, tools=None):
        import time

        yield StreamChunk(progress={"type": "reasoning_start"})
        for _ in range(3):
            yield StreamChunk(reasoning_delta="分析问题中…")
            time.sleep(0.15)
        yield StreamChunk(progress={"type": "reasoning_end"})
        for _ in range(3):
            yield StreamChunk(content_delta="fake response ")
            time.sleep(0.05)
        yield StreamChunk(
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 2},
        )


def main() -> int:
    with patch.object(main_mod, "create_model_client", lambda cfg, name: FakeClient()):
        try:
            main_mod.main.main(sys.argv[1:], standalone_mode=False)
        except SystemExit as exc:
            return int(exc.code or 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
