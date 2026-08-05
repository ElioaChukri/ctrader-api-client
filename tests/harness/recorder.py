"""Recording callbacks for observing what the system produced.

A `Recorder` is a plain async callable, so it can stand in anywhere a handler
or callback is expected. It stores what it was given and lets tests block until
the expected number of items has arrived -- no sleeps, no polling.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ctrader_api_client.auth import AccountCredentials
from ctrader_api_client.events import Event

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


class RecordingStore(Recorder[AccountCredentials]):
    """A `TokenStore` that records everything it was asked to persist.

    `fail_first` makes that many saves record and then raise, for exercising
    what a storage outage does to the refresh cycle.
    """

    def __init__(self, fail_first: int = 0) -> None:
        super().__init__()
        self._remaining_failures = fail_first

    async def save(self, credentials: AccountCredentials) -> None:
        """Record the credentials, failing the first `fail_first` calls."""
        await self(credentials)
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise RuntimeError("token store unavailable")


class RecordingPublisher(Recorder[Event]):
    """An `EventPublisher` that records everything published through it.

    Producers publish several kinds of event to the same bus, so the lookups
    here filter by type rather than assuming a test is the only thing emitting.
    """

    async def emit(self, event: Event) -> None:
        """Record the published event."""
        await self(event)

    def of[E: Event](self, event_type: type[E]) -> list[E]:
        """Every recorded event of the given type, in order."""
        return [event for event in self.items if isinstance(event, event_type)]

    def only_of[E: Event](self, event_type: type[E]) -> E:
        """The single recorded event of the given type.

        Raises:
            AssertionError: If there is not exactly one.
        """
        matches = self.of(event_type)
        if len(matches) != 1:
            raise AssertionError(f"expected exactly one {event_type.__name__}, got {len(matches)}: {matches!r}")
        return matches[0]

    async def wait_for_type(self, event_type: type[Event], count: int = 1, timeout: float = 5.0) -> None:
        """Block until at least `count` events of the given type have arrived."""
        await wait_until(lambda: len(self.of(event_type)) >= count, self._changed, timeout)


class RecordingRecovery:
    """A `SessionRecovery` that records the accounts it was told to restore."""

    def __init__(self) -> None:
        self.disconnected: list[int] = []

    async def handle_account_disconnect(self, account_id: int) -> None:
        """Record the disconnected account."""
        self.disconnected.append(account_id)


class RecordingRestorer:
    """A `SessionRestorer` that records the accounts it was asked about."""

    def __init__(self, before_each: Callable[[], None] | None = None) -> None:
        """Initialize the restorer.

        Args:
            before_each: Runs at the start of every call, for observing what
                else has or has not happened by the time restoration runs.
        """
        self.restored: list[int] = []
        self.forgotten: list[int] = []
        self._before_each = before_each

    async def restore(self, account_id: int) -> None:
        """Record the account whose subscriptions were to be re-applied."""
        if self._before_each is not None:
            self._before_each()
        self.restored.append(account_id)

    def forget(self, account_id: int) -> None:
        """Record the account whose subscriptions were to be discarded."""
        self.forgotten.append(account_id)
