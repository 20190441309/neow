"""What a running tool can ask of the agent loop that started it.

Some tools (``task``) run in a worker thread so the loop can show their
progress live. Such a tool reports progress with :func:`report_progress`
and runs anything that must happen on the loop's thread - asking the user
for approval - through :func:`run_on_loop`. Outside such a worker both
functions degrade gracefully: progress is dropped and ``run_on_loop`` calls
the function directly.
"""

import contextlib
import queue
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Optional

from neow.core.cancellation import CancelToken


@dataclass
class LoopChannel:
    """Queue from tool worker threads back to the agent loop's thread."""

    events: "queue.Queue[tuple]"
    cancel: CancelToken
    call_id: str = ""

    def progress(self, message: str) -> None:
        self.events.put(("progress", self.call_id, message))

    def call(self, func: Callable[[], Any], default: Any = None) -> Any:
        """Run *func* on the loop's thread; *default* if the turn is cancelled."""
        future: Future = Future()
        self.events.put(("call", func, future))
        while True:
            if self.cancel.cancelled():
                future.cancel()
                return default
            try:
                return future.result(timeout=0.1)
            except FutureTimeout:
                continue


_channel: ContextVar[Optional[LoopChannel]] = ContextVar("neow_loop", default=None)


@contextlib.contextmanager
def loop_channel(channel: LoopChannel) -> Iterator[LoopChannel]:
    reset = _channel.set(channel)
    try:
        yield channel
    finally:
        _channel.reset(reset)


def current_channel() -> Optional[LoopChannel]:
    return _channel.get()


def report_progress(message: str) -> None:
    """Show *message* on the running tool's card (no-op outside a worker)."""
    channel = _channel.get()
    if channel is not None:
        channel.progress(message)


def run_on_loop(func: Callable[[], Any], default: Any = None) -> Any:
    """Call *func* on the agent loop's thread (directly if already there)."""
    channel = _channel.get()
    if channel is None:
        return func()
    return channel.call(func, default)


__all__ = [
    "LoopChannel",
    "current_channel",
    "loop_channel",
    "report_progress",
    "run_on_loop",
]
