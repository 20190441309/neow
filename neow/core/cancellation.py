"""Cancellation shared by the UI, the agent loop and long-running tools."""

import contextlib
import threading
from contextvars import ContextVar
from typing import Iterator, Optional


class CancelToken:
    """Thread-safe cancellation flag shared by the UI and the loop."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def cancelled(self) -> bool:
        return self._event.is_set()


_current: ContextVar[Optional[CancelToken]] = ContextVar("neow_cancel", default=None)


def current_cancel_token() -> Optional[CancelToken]:
    """Token of the turn whose tool is running here, if any."""

    return _current.get()


@contextlib.contextmanager
def cancellation_scope(token: CancelToken) -> Iterator[CancelToken]:
    """Make *token* visible to tools run inside the block."""

    reset = _current.set(token)
    try:
        yield token
    finally:
        _current.reset(reset)


__all__ = ["CancelToken", "current_cancel_token", "cancellation_scope"]
