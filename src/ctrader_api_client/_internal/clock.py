"""Time source abstraction for timer-driven components."""

from __future__ import annotations

import time
from typing import Protocol as TypingProtocol

import anyio


class Clock(TypingProtocol):
    """A source of monotonic time and delays.

    Injected into components whose behaviour is driven by elapsed time so that
    those timings can be controlled deterministically instead of waited on.
    """

    def now(self) -> float:
        """Return the current value of a monotonic clock, in seconds."""
        ...

    async def sleep(self, seconds: float) -> None:
        """Suspend the calling task for the given number of seconds."""
        ...


class MonotonicClock:
    """Default clock backed by :func:`time.monotonic` and :func:`anyio.sleep`."""

    def now(self) -> float:
        """Return the current monotonic time in seconds."""
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        """Suspend the calling task for the given number of seconds."""
        await anyio.sleep(seconds)
