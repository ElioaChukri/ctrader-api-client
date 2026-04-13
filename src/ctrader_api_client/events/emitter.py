from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from .types import Event


logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Event)
EventHandler = Callable[[Any], Awaitable[None]]
ErrorHandler = Callable[[Event, EventHandler, Exception], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Subscription:
    """Internal subscription record."""

    handler: EventHandler
    account_id: int | None = None
    symbol_id: int | None = None


class EventEmitter:
    """Pub/sub event emitter with filtering.

    Allows subscribing to typed events with optional account_id and symbol_id
    filters. Handlers are called sequentially in registration order.

    Example:
        ```python
        emitter = EventEmitter()


        async def on_spot(event: SpotEvent):
            print(f"Price: {event.bid}/{event.ask}")


        emitter.subscribe(SpotEvent, on_spot, symbol_id=1)

        # Later, when event arrives:
        await emitter.emit(spot_event)
        ```
    """

    def __init__(
        self,
        on_handler_error: ErrorHandler | None = None,
    ) -> None:
        """Initialize the event emitter.

        Args:
            on_handler_error: Optional async callback invoked when a handler
                raises an exception. Receives the event, handler, and exception.
                Called after logging the error.
        """
        self._subscriptions: dict[type[Event], list[Subscription]] = {}
        self._on_handler_error = on_handler_error

    def subscribe(
        self,
        event_type: type[T],
        handler: Callable[[T], Awaitable[None]],
        *,
        account_id: int | None = None,
        symbol_id: int | None = None,
    ) -> None:
        """Subscribe to an event type.

        Since handlers are called sequentially, it is highly recommended to include account_id or symbol_id filters
        to avoid unnecessary handler invocations. In applications where many different accounts are handled,
        the number handlers for an event can easily grow to hundreds or thousands, and without filters every handler
        will be called for every event, causing significant performance issues.


        Args:
            event_type: The event class to subscribe to.
            handler: Async function to call when event occurs.
            account_id: Only receive events for this account (optional).
                Raises ValueError if event_type doesn't have an account_id field.
            symbol_id: Only receive events for this symbol (optional).
                Raises ValueError if event_type doesn't have a symbol_id field.

        Raises:
            ValueError: If a filter is provided but the event type doesn't have that field.
        """
        # Validate that event type supports the requested filters
        if account_id is not None:
            self._validate_filter(event_type, "account_id")
        if symbol_id is not None:
            self._validate_filter(event_type, "symbol_id")

        if event_type not in self._subscriptions:
            self._subscriptions[event_type] = []

        subscription = Subscription(
            handler=handler,
            account_id=account_id,
            symbol_id=symbol_id,
        )
        self._subscriptions[event_type].append(subscription)

        logger.debug(
            "Subscribed %s to %s (account=%s, symbol=%s)",
            getattr(handler, "__name__", repr(handler)),
            event_type.__name__,
            account_id,
            symbol_id,
        )

    def unsubscribe(
        self,
        event_type: type[T],
        handler: Callable[[T], Awaitable[None]],
    ) -> bool:
        """Unsubscribe a handler from an event type.

        Removes the first matching subscription for this handler.

        Args:
            event_type: The event class to unsubscribe from.
            handler: The handler function to remove.

        Returns:
            True if handler was found and removed, False otherwise.
        """
        if event_type not in self._subscriptions:
            return False

        subscriptions = self._subscriptions[event_type]
        for i, sub in enumerate(subscriptions):
            if sub.handler is handler:
                subscriptions.pop(i)
                logger.debug(
                    "Unsubscribed %s from %s",
                    getattr(handler, "__name__", repr(handler)),
                    event_type.__name__,
                )
                return True

        return False

    def unsubscribe_all(
        self,
        event_type: type[T] | None = None,
    ) -> int:
        """Unsubscribe all handlers.

        Args:
            event_type: If provided, only unsubscribe handlers for this type.
                If None, unsubscribe all handlers for all types.

        Returns:
            Number of subscriptions removed.
        """
        if event_type is not None:
            count = len(self._subscriptions.get(event_type, []))
            self._subscriptions[event_type] = []
            logger.debug("Unsubscribed all handlers from %s", event_type.__name__)
            return count

        count = sum(len(subs) for subs in self._subscriptions.values())
        self._subscriptions.clear()
        logger.debug("Unsubscribed all handlers from all events")
        return count

    async def emit(self, event: Event) -> None:
        """Emit an event to all matching subscribers.

        Handlers are called sequentially in registration order. This is to ensure predictable behavior when
        multiple handlers are registered for the same event type. If handlers were called concurrently,
        the order of execution would be non-deterministic, which could lead to inconsistent behavior for users.

        If a handler raises, the error is logged and the optional error callback is invoked, then remaining handlers
        continue.

        Args:
            event: The event to emit.
        """
        event_type = type(event)
        subscriptions = self._subscriptions.get(event_type, [])

        for sub in subscriptions:
            if not self._matches_filter(event, sub):
                continue

            try:
                await sub.handler(event)
            except Exception as e:
                logger.error(
                    "Handler %s raised %s for %s: %s",
                    getattr(sub.handler, "__name__", repr(sub.handler)),
                    type(e).__name__,
                    event_type.__name__,
                    e,
                )
                if self._on_handler_error is not None:
                    try:
                        await self._on_handler_error(event, sub.handler, e)
                    except Exception as callback_error:
                        logger.error(
                            "Error callback raised %s: %s",
                            type(callback_error).__name__,
                            callback_error,
                        )

    @staticmethod
    def _validate_filter(event_type: type, field_name: str) -> None:
        """Validate that an event type supports filtering by a field.

        Args:
            event_type: The event class to check.
            field_name: The field name to filter by.

        Raises:
            ValueError: If the event type doesn't have the specified field.
        """
        dataclass_fields = getattr(event_type, "__dataclass_fields__", {})
        if field_name not in dataclass_fields:
            raise ValueError(
                f"{event_type.__name__} does not have a '{field_name}' field "
                f"and cannot be filtered by it. Remove the {field_name} parameter."
            )

    @staticmethod
    def _matches_filter(event: Event, sub: Subscription) -> bool:
        """Check if event matches subscription filters."""
        # Check account_id filter
        if sub.account_id is not None:
            event_account_id = getattr(event, "account_id", None)
            if event_account_id != sub.account_id:
                return False

        # Check symbol_id filter
        if sub.symbol_id is not None:
            event_symbol_id = getattr(event, "symbol_id", None)
            if event_symbol_id != sub.symbol_id:
                return False

        return True

    def subscription_count(self, event_type: type[T] | None = None) -> int:
        """Get the number of active subscriptions.

        Args:
            event_type: If provided, count only for this type.
                If None, count all subscriptions.

        Returns:
            Number of active subscriptions.
        """
        if event_type is not None:
            return len(self._subscriptions.get(event_type, []))
        return sum(len(subs) for subs in self._subscriptions.values())
