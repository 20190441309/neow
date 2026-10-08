"""Chat controller: run a conversation turn and emit UI events.

``run_turn`` is blocking and is meant to be called from a worker thread;
every notification goes through ``event_callback`` (the UI marshals it back
to the main thread).  The controller mirrors the classic REPL's turn
prelude: URL auto-fetch, ``pre_prompt`` plugin event and the token limit
guard (see ``neow/cli/repl.py:1049-1060``).
"""

from __future__ import annotations

import re
import threading
import time
from concurrent.futures import CancelledError as FutureCancelledError
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, Callable, Dict, Optional

from neow.core.agent_loop import CancelToken
from neow.tui.bridge.events import (
    ContentDelta,
    Notice,
    ReasoningDelta,
    ReasoningEnd,
    ReasoningStarted,
    ToolFinished,
    ToolStarted,
    TurnCompleted,
    TurnFailed,
)

URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")


def _is_error(result: str) -> bool:
    return result.startswith("Error:")


def _is_denied(result: str) -> bool:
    return "User denied" in result


class ChatController:
    """Owns one conversation turn's lifecycle."""

    def __init__(
        self,
        conversation: Any,
        *,
        event_callback: Callable[[Any], None],
        approval_bridge: Optional[Callable[[str, dict, str], bool]] = None,
        token_tracker: Any = None,
        event_bus: Any = None,
        web_fetcher: Any = None,
        flush_interval: float = 0.05,
        time_fn: Callable[[], float] = time.monotonic,
    ):
        self._conversation = conversation
        self._emit = event_callback
        self.approval_bridge = approval_bridge
        self._token_tracker = token_tracker
        self._event_bus = event_bus
        self._web_fetcher = web_fetcher
        self.flush_interval = flush_interval
        self._time_fn = time_fn
        self._busy = False
        self._cancel = threading.Event()
        self._token = CancelToken()
        self._content = ""
        self._reasoning = ""
        self._pending_content = ""
        self._pending_reasoning = ""
        self._last_flush = 0.0
        self._turn_start = 0.0

    # -- public API ----------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._busy

    def cancel(self) -> None:
        self._cancel.set()
        self._token.cancel()

    def run_turn(self, user_input: str) -> None:
        """Consume the conversation stream; blocking (call from a worker)."""

        self._busy = True
        self._cancel.clear()
        self._token = CancelToken()
        self._content = ""
        self._reasoning = ""
        self._pending_content = ""
        self._pending_reasoning = ""
        self._turn_start = self._time_fn()
        self._last_flush = self._turn_start
        try:
            self._prelude(user_input)
            if self._token_tracker and self._token_tracker.check_max_tokens():
                self._emit(
                    TurnFailed(
                        "Token limit reached. Use /compact to summarize history."
                    )
                )
                return

            if hasattr(self._conversation, "on_cancel"):
                self._conversation.on_cancel = self.cancel

            stream = self._conversation.get_response_stream(
                user_input, cancel=self._token
            )
            cancelled = False
            usage: Optional[Dict[str, int]] = None
            try:
                for chunk in stream:
                    if self._cancel.is_set():
                        cancelled = True
                        try:
                            stream.close()
                        except Exception:
                            pass
                        break
                    self._handle_chunk(chunk)
                    usage = getattr(chunk, "usage", None) or usage
                    self._maybe_flush()
            finally:
                self._flush_all()
            self._emit(
                TurnCompleted(content=self._content, usage=usage, cancelled=cancelled)
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a UI event
            self._emit(TurnFailed(str(exc)))
        finally:
            self._busy = False

    # -- turn internals ------------------------------------------------

    def _prelude(self, user_input: str) -> None:
        if self._web_fetcher is not None and hasattr(
            self._conversation, "add_web_content"
        ):
            cache = getattr(self._conversation, "web_cache", {}) or {}
            for url in URL_PATTERN.findall(user_input):
                if url in cache:
                    continue
                try:
                    content = self._web_fetcher.fetch(url)
                    self._conversation.add_web_content(url, content)
                except Exception:
                    continue
        if self._event_bus is not None:
            self._event_bus.emit(
                "pre_prompt", prompt=user_input, conversation=self._conversation
            )

    def _handle_chunk(self, chunk: Any) -> None:
        progress = getattr(chunk, "progress", None) or {}
        ptype = progress.get("type")
        if ptype == "reasoning_start":
            self._emit(ReasoningStarted())
        elif ptype == "reasoning_end":
            self._flush_reasoning()
            self._emit(
                ReasoningEnd(
                    reasoning=self._reasoning,
                    duration=self._time_fn() - self._turn_start,
                )
            )
        elif ptype == "tool_start":
            self._flush_all()
            self._emit(
                ToolStarted(
                    name=progress.get("name", ""),
                    args=progress.get("args", {}) or {},
                    call_id=progress.get("id", ""),
                )
            )
        elif ptype == "tool_end":
            self._flush_all()
            result = progress.get("result", "")
            self._emit(
                ToolFinished(
                    name=progress.get("name", ""),
                    result=result,
                    is_error=_is_error(result),
                    denied=_is_denied(result),
                    call_id=progress.get("id", ""),
                )
            )
        elif ptype == "notice":
            self._flush_all()
            self._emit(
                Notice(
                    message=progress.get("message", ""),
                    level=progress.get("level", "info"),
                )
            )
        if getattr(chunk, "reasoning_delta", ""):
            self._reasoning += chunk.reasoning_delta
            self._pending_reasoning += chunk.reasoning_delta
        if getattr(chunk, "content_delta", ""):
            self._content += chunk.content_delta
            self._pending_content += chunk.content_delta

    def _maybe_flush(self) -> None:
        now = self._time_fn()
        if now - self._last_flush >= self.flush_interval:
            self._flush_all()
            self._last_flush = now

    def _flush_reasoning(self) -> None:
        if self._pending_reasoning:
            self._emit(ReasoningDelta(self._pending_reasoning))
            self._pending_reasoning = ""

    def _flush_content(self) -> None:
        if self._pending_content:
            self._emit(ContentDelta(self._pending_content))
            self._pending_content = ""

    def _flush_all(self) -> None:
        self._flush_reasoning()
        self._flush_content()


__all__ = ["ChatController", "ApprovalBridge"]


class ApprovalBridge:
    """Thread-safe bridge from a worker thread to a UI approval modal.

    ``request`` runs on the worker thread and must schedule the modal on
    the UI thread without blocking (e.g. ``app.call_from_thread``).  The
    bridge blocks the worker on a ``Future`` with a timeout, defaulting to
    denial on timeout/cancellation/errors so the process never hangs.
    """

    def __init__(
        self,
        *,
        request: Callable[[str, Dict[str, Any], str, Future], None],
        timeout: float = 600.0,
    ):
        self._request = request
        self.timeout = timeout

    def __call__(self, tool: str, params: Dict[str, Any], reason: str) -> bool:
        future: Future = Future()
        try:
            self._request(tool, params, reason, future)
        except Exception:
            return False
        try:
            return bool(future.result(timeout=self.timeout))
        except (FutureTimeoutError, FutureCancelledError):
            return False
        except Exception:
            return False
