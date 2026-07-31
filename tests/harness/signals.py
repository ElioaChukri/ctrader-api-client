"""Edge-triggered signalling and predicate waiting.

Tests must never poll with arbitrary sleeps -- that is the main source of
flakiness. Instead, harness components `notify()` a `Signal` whenever
observable state changes, and tests block in `wait_until()` until the state
they care about holds.
"""

from __future__ import annotations

from collections.abc import Callable

import anyio


class Signal:
    """A repeatable, edge-triggered notification.

    `anyio.Event` cannot be reset, so each `notify()` fires the current event
    and installs a fresh one for subsequent waiters.
    """

    def __init__(self) -> None:
        self._event = anyio.Event()

    def notify(self) -> None:
        """Wake every current waiter."""
        event = self._event
        self._event = anyio.Event()
        event.set()

    async def wait(self) -> None:
        """Block until the next `notify()`."""
        # Snapshot before awaiting: notify() swaps the attribute, and a waiter
        # that re-read it after waking would miss the edge it was waiting for.
        event = self._event
        await event.wait()


async def wait_until(
    predicate: Callable[[], bool],
    signal: Signal,
    timeout: float = 5.0,
) -> None:
    """Block until `predicate` holds, waking on each `signal.notify()`.

    Args:
        predicate: Condition to wait for. Checked immediately and after each
            notification.
        signal: The signal fired whenever the underlying state changes.
        timeout: Seconds before giving up.

    Raises:
        TimeoutError: If the predicate does not hold within `timeout`.
    """
    with anyio.fail_after(timeout):
        while not predicate():
            await signal.wait()
