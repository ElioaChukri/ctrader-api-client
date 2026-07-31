"""Recording callbacks for observing what the system produced.

A `Recorder` is a plain async callable, so it can stand in anywhere a handler
or callback is expected. It stores what it was given and lets tests block until
the expected number of items has arrived -- no sleeps, no polling.
"""

from __future__ import annotations

from typing import Any

from .signals import Signal, wait_until


class Recorder[T]:
    """An async callable that records everything passed to it."""

    def __init__(self) -> None:
        self.items: list[Any] = []
        self._changed = Signal()

    async def __call__(self, *args: Any) -> None:
        """Record the call arguments.

        A single argument is stored as-is; multiple arguments are stored as a
        tuple, which suits multi-argument callbacks such as `on_account_ready`.
        """
        self.items.append(args[0] if len(args) == 1 else args)
        self._changed.notify()

    @property
    def count(self) -> int:
        """How many times this recorder has been called."""
        return len(self.items)

    @property
    def only(self) -> Any:
        """The single recorded item.

        Raises:
            AssertionError: If there is not exactly one.
        """
        if len(self.items) != 1:
            raise AssertionError(f"expected exactly one recorded item, got {len(self.items)}: {self.items!r}")
        return self.items[0]

    @property
    def last(self) -> Any:
        """The most recently recorded item.

        Raises:
            AssertionError: If nothing has been recorded.
        """
        if not self.items:
            raise AssertionError("nothing was recorded")
        return self.items[-1]

    async def wait_for(self, count: int = 1, timeout: float = 5.0) -> None:
        """Block until at least `count` items have been recorded."""
        await wait_until(lambda: len(self.items) >= count, self._changed, timeout)


class FailingRecorder[T](Recorder[T]):
    """A recorder that records and then raises, for error-isolation tests."""

    def __init__(self, error: Exception | None = None) -> None:
        super().__init__()
        self._error = error if error is not None else RuntimeError("handler failed")

    async def __call__(self, *args: Any) -> None:
        """Record the call, then raise."""
        await super().__call__(*args)
        raise self._error
