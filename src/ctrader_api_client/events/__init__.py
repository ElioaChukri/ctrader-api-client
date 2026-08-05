"""Event system for cTrader API client.

This module provides a pub/sub mechanism for handling async events from
the cTrader server, such as price updates, order executions, and account
changes.

Example:
    ```python
    from ctrader_api_client.events import EventEmitter, SpotEvent

    emitter = EventEmitter()


    async def on_price(event: SpotEvent):
        print(f"{event.symbol_id}: {event.bid}/{event.ask}")


    emitter.subscribe(SpotEvent, on_price, symbol_id=1)
    ```
"""

from .emitter import EventEmitter
from .publisher import EventPublisher
from .router import EventRouter
from .types import (
    AccountDisconnectEvent,
    ClientDisconnectEvent,
    DepthEvent,
    DepthQuote,
    Event,
    ExecutionEvent,
    MarginCallTriggerEvent,
    MarginChangeEvent,
    OrderErrorEvent,
    ReadyEvent,
    ReconnectedEvent,
    SpotEvent,
    SubscriptionRestoreFailedEvent,
    SymbolChangedEvent,
    TokenInvalidatedEvent,
    TokenRefreshFailedEvent,
    TraderUpdateEvent,
    TrailingStopChangedEvent,
)


__all__ = [
    "AccountDisconnectEvent",
    "ClientDisconnectEvent",
    "DepthEvent",
    "DepthQuote",
    "Event",
    "EventEmitter",
    "EventPublisher",
    "EventRouter",
    "ExecutionEvent",
    "MarginCallTriggerEvent",
    "MarginChangeEvent",
    "OrderErrorEvent",
    "ReadyEvent",
    "ReconnectedEvent",
    "SpotEvent",
    "SubscriptionRestoreFailedEvent",
    "SymbolChangedEvent",
    "TokenInvalidatedEvent",
    "TokenRefreshFailedEvent",
    "TraderUpdateEvent",
    "TrailingStopChangedEvent",
]
