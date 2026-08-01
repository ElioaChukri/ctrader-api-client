from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import betterproto

from .._internal import DEFAULT_MONEY_DIGITS, timestamp_to_datetime
from .._internal.proto import (
    ProtoOAAccountDisconnectEvent,
    ProtoOAAccountsTokenInvalidatedEvent,
    ProtoOAClientDisconnectEvent,
    ProtoOADepthEvent,
    ProtoOAExecutionEvent,
    ProtoOAMarginCallTriggerEvent,
    ProtoOAMarginChangedEvent,
    ProtoOAOrderErrorEvent,
    ProtoOASpotEvent,
    ProtoOASymbolChangedEvent,
    ProtoOATraderUpdatedEvent,
    ProtoOATrailingSLChangedEvent,
)
from ..models import Trendbar
from ._execution import execution_event_from_proto
from .emitter import EventEmitter
from .types import (
    AccountDisconnectEvent,
    ClientDisconnectEvent,
    DepthEvent,
    DepthQuote,
    MarginCallTriggerEvent,
    MarginChangeEvent,
    OrderErrorEvent,
    SpotEvent,
    SymbolChangedEvent,
    TokenInvalidatedEvent,
    TraderUpdateEvent,
    TrailingStopChangedEvent,
)


if TYPE_CHECKING:
    from ..connection.protocol import Protocol


logger = logging.getLogger(__name__)


class EventRouter:
    """Routes proto events from Protocol to typed events on EventEmitter.

    Registers handlers for all relevant proto event types with the Protocol,
    converts them to typed event dataclasses, and emits them through the
    EventEmitter.

    Example:
        ```python
        router = EventRouter(protocol, emitter)
        router.start()

        # Now proto events will be converted and emitted
        # ...

        router.stop()
        ```
    """

    def __init__(
        self,
        protocol: Protocol,
        emitter: EventEmitter,
    ) -> None:
        """Initialize the event router.

        Args:
            protocol: The protocol instance to receive proto events from.
            emitter: The event emitter to publish typed events to.
        """
        self._protocol = protocol
        self._emitter = emitter
        self._started = False

    @property
    def is_started(self) -> bool:
        """Whether the router is currently started."""
        return self._started

    def start(self) -> None:
        """Idempotent. Register handlers for all proto event types."""
        if self._started:
            return

        self._protocol.on_event(ProtoOASpotEvent, self._handle_spot)
        self._protocol.on_event(ProtoOAExecutionEvent, self._handle_execution)
        self._protocol.on_event(ProtoOAOrderErrorEvent, self._handle_order_error)
        self._protocol.on_event(ProtoOATraderUpdatedEvent, self._handle_trader_update)
        self._protocol.on_event(ProtoOAMarginChangedEvent, self._handle_margin_change)
        self._protocol.on_event(ProtoOADepthEvent, self._handle_depth)
        self._protocol.on_event(
            ProtoOAAccountsTokenInvalidatedEvent,
            self._handle_token_invalidated,
        )
        self._protocol.on_event(
            ProtoOAClientDisconnectEvent,
            self._handle_client_disconnect,
        )
        self._protocol.on_event(
            ProtoOAAccountDisconnectEvent,
            self._handle_account_disconnect,
        )
        self._protocol.on_event(ProtoOASymbolChangedEvent, self._handle_symbol_changed)
        self._protocol.on_event(
            ProtoOATrailingSLChangedEvent,
            self._handle_trailing_stop_changed,
        )
        self._protocol.on_event(
            ProtoOAMarginCallTriggerEvent,
            self._handle_margin_call_trigger,
        )

        self._started = True
        logger.debug("Event router started")

    def stop(self) -> None:
        """Idempotent. Unregister all proto event handlers."""
        if not self._started:
            return

        self._protocol.remove_handler(ProtoOASpotEvent, self._handle_spot)
        self._protocol.remove_handler(ProtoOAExecutionEvent, self._handle_execution)
        self._protocol.remove_handler(ProtoOAOrderErrorEvent, self._handle_order_error)
        self._protocol.remove_handler(ProtoOATraderUpdatedEvent, self._handle_trader_update)
        self._protocol.remove_handler(ProtoOAMarginChangedEvent, self._handle_margin_change)
        self._protocol.remove_handler(ProtoOADepthEvent, self._handle_depth)
        self._protocol.remove_handler(
            ProtoOAAccountsTokenInvalidatedEvent,
            self._handle_token_invalidated,
        )
        self._protocol.remove_handler(
            ProtoOAClientDisconnectEvent,
            self._handle_client_disconnect,
        )
        self._protocol.remove_handler(
            ProtoOAAccountDisconnectEvent,
            self._handle_account_disconnect,
        )
        self._protocol.remove_handler(ProtoOASymbolChangedEvent, self._handle_symbol_changed)
        self._protocol.remove_handler(
            ProtoOATrailingSLChangedEvent,
            self._handle_trailing_stop_changed,
        )
        self._protocol.remove_handler(
            ProtoOAMarginCallTriggerEvent,
            self._handle_margin_call_trigger,
        )

        self._started = False
        logger.debug("Event router stopped")

    # -------------------------------------------------------------------------
    # Proto to Event Converters
    # -------------------------------------------------------------------------

    async def _handle_spot(self, proto: ProtoOASpotEvent) -> None:
        """Convert ProtoOASpotEvent to SpotEvent."""

        # I don't trust the API
        if proto.trendbar is None:
            trendbars = []  # type: ignore[unreachable]
        else:
            trendbars = [Trendbar.from_proto(tb, bid_price=Decimal(proto.bid)) for tb in proto.trendbar]
        event = SpotEvent(
            account_id=proto.ctid_trader_account_id,
            symbol_id=proto.symbol_id,
            bid=proto.bid / Decimal(100000) if proto.bid else None,
            ask=proto.ask / Decimal(100000) if proto.ask else None,
            timestamp=timestamp_to_datetime(proto.timestamp) if proto.timestamp else datetime.now(UTC),
            trendbar=trendbars,
        )
        await self._emitter.emit(event)

    async def _handle_execution(self, proto: ProtoOAExecutionEvent) -> None:
        """Convert ProtoOAExecutionEvent to ExecutionEvent."""
        event = execution_event_from_proto(proto)

        if event is None:
            logger.warning("Unknown execution type %s in ProtoOAExecutionEvent", proto.execution_type)
            return

        logger.debug(
            "Execution: %s account=%d order=%d",
            event.execution_type.name,
            event.account_id,
            event.order_id,
        )
        await self._emitter.emit(event)

    async def _handle_order_error(self, proto: ProtoOAOrderErrorEvent) -> None:
        """Convert ProtoOAOrderErrorEvent to OrderErrorEvent."""
        event = OrderErrorEvent(
            account_id=proto.ctid_trader_account_id,
            order_id=proto.order_id if proto.order_id else None,
            position_id=proto.position_id if proto.position_id else None,
            error_code=proto.error_code,
            description=proto.description or "",
        )
        logger.warning(
            "Order error: account=%d order=%s error=%s: %s",
            event.account_id,
            event.order_id,
            event.error_code,
            event.description,
        )
        await self._emitter.emit(event)

    async def _handle_trader_update(self, proto: ProtoOATraderUpdatedEvent) -> None:
        """Convert ProtoOATraderUpdatedEvent to TraderUpdateEvent."""
        trader = proto.trader
        if not betterproto.serialized_on_wire(trader):
            logger.warning("Ignoring ProtoOATraderUpdatedEvent without trader data")
            return

        event = TraderUpdateEvent(
            account_id=proto.ctid_trader_account_id,
            balance=trader.balance,
            leverage_in_cents=trader.leverage_in_cents if trader.leverage_in_cents else None,
            money_digits=trader.money_digits or DEFAULT_MONEY_DIGITS,
        )
        await self._emitter.emit(event)

    async def _handle_margin_change(self, proto: ProtoOAMarginChangedEvent) -> None:
        """Convert ProtoOAMarginChangedEvent to MarginChangeEvent."""
        event = MarginChangeEvent(
            account_id=proto.ctid_trader_account_id,
            position_id=proto.position_id,
            used_margin=proto.used_margin,
            money_digits=proto.money_digits or DEFAULT_MONEY_DIGITS,
        )
        await self._emitter.emit(event)

    async def _handle_depth(self, proto: ProtoOADepthEvent) -> None:
        """Convert ProtoOADepthEvent to DepthEvent."""
        # Convert depth quotes
        new_quotes: list[DepthQuote] = []
        for q in proto.new_quotes:
            # Each quote has either bid or ask set, not both
            if q.bid:
                new_quotes.append(
                    DepthQuote(
                        quote_id=q.id,
                        price=q.bid,
                        size=q.size,
                        is_bid=True,
                    )
                )
            elif q.ask:
                new_quotes.append(
                    DepthQuote(
                        quote_id=q.id,
                        price=q.ask,
                        size=q.size,
                        is_bid=False,
                    )
                )

        event = DepthEvent(
            account_id=proto.ctid_trader_account_id,
            symbol_id=proto.symbol_id,
            new_quotes=tuple(new_quotes),
            deleted_quote_ids=tuple(proto.deleted_quotes),
        )
        await self._emitter.emit(event)

    async def _handle_token_invalidated(
        self,
        proto: ProtoOAAccountsTokenInvalidatedEvent,
    ) -> None:
        """Convert ProtoOAAccountsTokenInvalidatedEvent to TokenInvalidatedEvent."""
        event = TokenInvalidatedEvent(
            account_ids=tuple(proto.ctid_trader_account_ids),
            reason=proto.reason or "Unknown",
        )
        logger.warning("Access token invalidated for accounts: %s", list(event.account_ids))
        await self._emitter.emit(event)

    async def _handle_client_disconnect(
        self,
        proto: ProtoOAClientDisconnectEvent,
    ) -> None:
        """Convert ProtoOAClientDisconnectEvent to ClientDisconnectEvent."""
        event = ClientDisconnectEvent(
            reason=proto.reason or "Unknown",
        )
        logger.warning("Client disconnected by server: %s", event.reason)
        await self._emitter.emit(event)

    async def _handle_account_disconnect(
        self,
        proto: ProtoOAAccountDisconnectEvent,
    ) -> None:
        """Convert ProtoOAAccountDisconnectEvent to AccountDisconnectEvent."""
        event = AccountDisconnectEvent(
            account_id=proto.ctid_trader_account_id,
        )
        logger.warning("Account %d disconnected by server", event.account_id)
        await self._emitter.emit(event)

    async def _handle_symbol_changed(
        self,
        proto: ProtoOASymbolChangedEvent,
    ) -> None:
        """Convert ProtoOASymbolChangedEvent to SymbolChangedEvent."""
        event = SymbolChangedEvent(
            account_id=proto.ctid_trader_account_id,
            symbol_ids=tuple(proto.symbol_id),
        )
        await self._emitter.emit(event)

    async def _handle_trailing_stop_changed(
        self,
        proto: ProtoOATrailingSLChangedEvent,
    ) -> None:
        """Convert ProtoOATrailingSLChangedEvent to TrailingStopChangedEvent."""
        event = TrailingStopChangedEvent(
            account_id=proto.ctid_trader_account_id,
            position_id=proto.position_id,
            order_id=proto.order_id,
            stop_price=Decimal(str(proto.stop_price)),
            timestamp=timestamp_to_datetime(proto.utc_last_update_timestamp),
        )
        await self._emitter.emit(event)

    async def _handle_margin_call_trigger(
        self,
        proto: ProtoOAMarginCallTriggerEvent,
    ) -> None:
        """Convert ProtoOAMarginCallTriggerEvent to MarginCallTriggerEvent."""
        margin_call = proto.margin_call
        event = MarginCallTriggerEvent(
            account_id=proto.ctid_trader_account_id,
            margin_call_type=margin_call.margin_call_type,
            margin_level_threshold=Decimal(str(margin_call.margin_level_threshold)),
        )
        logger.error("Margin call triggered: account=%d type=%s", event.account_id, event.margin_call_type)
        await self._emitter.emit(event)
