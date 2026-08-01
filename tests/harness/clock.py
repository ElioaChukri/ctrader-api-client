"""A clock whose passage of time is driven by the test, not by the wall.

Heartbeat cadence, inactivity timeouts, token-refresh polling and recovery
backoff are all time-driven. Testing them against real time means either slow
tests or flaky ones. `ManualClock` implements the same `Clock` protocol the
production code depends on, so those behaviours become fully deterministic:
nothing advances until the test says so.

Typical use::

    await clock.wait_for_sleepers()  # loop is parked on its next sleep
    await clock.advance(interval)  # release it
    await wait_until(...)  # observe the resulting behaviour
"""

from __future__ import annotations

import anyio

from .signals import Signal, wait_until


class ManualClock:
    """Deterministic `Clock` implementation controlled by `advance()`."""

    def __init__(self, start: float = 1_000.0) -> None:
        """Initialize the clock.

        Args:
            start: Initial reading, in seconds. Non-zero by default so that
                code comparing against an unset `0.0` timestamp stands out.
        """
        self._now = start
        self._sleepers: list[tuple[float, anyio.Event]] = []
        self._changed = Signal()

    def now(self) -> float:
        """Return the current reading, in seconds."""
        return self._now

    async def sleep(self, seconds: float) -> None:
        """Block until the clock is advanced past `seconds` from now."""
        if seconds <= 0:
            await anyio.sleep(0)
            return

        deadline = self._now + seconds
        event = anyio.Event()
        entry = (deadline, event)
        self._sleepers.append(entry)
        self._changed.notify()
        try:
            await event.wait()
        finally:
            # A cancelled sleeper must not linger, or `wait_for_sleepers`
            # would count a task that is no longer waiting for anything.
            if entry in self._sleepers:
                self._sleepers.remove(entry)
                self._changed.notify()

    @property
    def sleeper_count(self) -> int:
        """How many tasks are currently parked in `sleep()`."""
        return len(self._sleepers)

    async def wait_for_sleepers(self, count: int = 1, timeout: float = 5.0) -> None:
        """Block until at least `count` tasks are parked in `sleep()`.

        Call this before `advance()` to remove the race between a background
        loop starting and the test moving time forward.
        """
        await wait_until(lambda: len(self._sleepers) >= count, self._changed, timeout)

    async def advance(self, seconds: float) -> None:
        """Move the clock forward, releasing every sleeper that comes due.

        Time jumps to the new reading *before* sleepers are woken, so a task
        that slept for one interval across a ten-interval jump observes the
        full elapsed time -- which is what a real process sees after being
        starved or after the machine suspends.

        Tasks that re-arm a sleep while this call is running are scheduled
        relative to the new reading, so they wake on a later `advance()` rather
        than looping here.
        """
        self._now += seconds

        due = sorted(
            (entry for entry in self._sleepers if entry[0] <= self._now),
            key=lambda entry: entry[0],
        )
        for entry in due:
            self._sleepers.remove(entry)
            entry[1].set()
            # Let the woken task run up to its next suspension point.
            await anyio.sleep(0)

        self._changed.notify()
        await anyio.sleep(0)
