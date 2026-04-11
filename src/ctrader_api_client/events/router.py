from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from .._internal.proto import (
    ProtoOAAccountDisconnectEvent,
    ProtoOAAccountsTokenInvalidatedEvent,
    ProtoOAClientDisconnectEvent,
    ProtoOADepthEvent,
    ProtoOAExecutionEvent,
    ProtoOAExecutionType,
    ProtoOAMarginCallTriggerEvent,
    ProtoOAMarginChangedEvent,
    ProtoOAOrderErrorEvent,
    ProtoOASpotEvent,
    ProtoOASymbolChangedEvent,
    ProtoOATraderUpdatedEvent,
    ProtoOATrailingSLChangedEvent,
    ProtoOAv1PnLChangeEvent,
)
from ..enums import ExecutionType, OrderSide
from .emitter import EventEmitter
from .types import (
    AccountDisconnectEvent,
    ClientDisconnectEvent,
    DepthEvent,
    DepthQuote,
    ExecutionEvent,
    MarginCallTriggerEvent,
    MarginChangeEvent,
    OrderErrorEvent,
    PnLChangeEvent,
    SpotEvent,
    SymbolChangedEvent,
    TokenInvalidatedEvent,
    TraderUpdateEvent,
    TrailingStopChangedEvent,
)


if TYPE_CHECKING:
    from ..connection.protocol import Protocol


logger = logging.getLogger(__name__)


# Map ProtoOAExecutionType enum values to our ExecutionType
_EXECUTION_TYPE_MAP: dict[int, ExecutionType] = {
    ProtoOAExecutionType.ORDER_ACCEPTED: ExecutionType.ORDER_ACCEPTED,
    ProtoOAExecutionType.ORDER_FILLED: ExecutionType.ORDER_FILLED,
    ProtoOAExecutionType.ORDER_REPLACED: ExecutionType.ORDER_REPLACED,
    ProtoOAExecutionType.ORDER_CANCELLED: ExecutionType.ORDER_CANCELLED,
    ProtoOAExecutionType.ORDER_EXPIRED: ExecutionType.ORDER_EXPIRED,
    ProtoOAExecutionType.ORDER_REJECTED: ExecutionType.ORDER_REJECTED,
    ProtoOAExecutionType.ORDER_CANCEL_REJECTED: ExecutionType.ORDER_CANCEL_REJECTED,
    ProtoOAExecutionType.SWAP: ExecutionType.SWAP,
    ProtoOAExecutionType.DEPOSIT_WITHDRAW: ExecutionType.DEPOSIT_WITHDRAW,
    ProtoOAExecutionType.ORDER_PARTIAL_FILL: ExecutionType.ORDER_PARTIAL_FILL,
    ProtoOAExecutionType.BONUS_DEPOSIT_WITHDRAW: ExecutionType.BONUS_DEPOSIT_WITHDRAW,
}


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
        self._protocol.on_event(ProtoOAv1PnLChangeEvent, self._handle_pnl_change)

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
        self._protocol.remove_handler(ProtoOAv1PnLChangeEvent, self._handle_pnl_change)

        self._started = False
        logger.debug("Event router stopped")

    # -------------------------------------------------------------------------
    # Proto to Event Converters
    # -------------------------------------------------------------------------

    async def _handle_spot(self, proto: ProtoOASpotEvent) -> None:
        """Convert ProtoOASpotEvent to SpotEvent."""
        event = SpotEvent(
            account_id=proto.ctid_trader_account_id,
            symbol_id=proto.symbol_id,
            bid=proto.bid if proto.bid else None,
            ask=proto.ask if proto.ask else None,
            timestamp=self._timestamp_to_datetime(proto.timestamp) if proto.timestamp else datetime.now(UTC),
        )
        await self._emitter.emit(event)

    async def _handle_execution(self, proto: ProtoOAExecutionEvent) -> None:
        """Convert ProtoOAExecutionEvent to ExecutionEvent."""
        # Map execution type
        exec_type = _EXECUTION_TYPE_MAP.get(proto.execution_type)

        if exec_type is None:
            logger.warning("Unknown execution type %s in ProtoOAExecutionEvent", proto.execution_type)
            return

        # Map order side
        side = OrderSide.BUY
        if proto.order and proto.order.trade_data:
            # ProtoOATradeSide: BUY=1, SELL=2
            if proto.order.trade_data.trade_side == 2:
                side = OrderSide.SELL

        # Extract order details
        order_id = proto.order.order_id if proto.order else 0
        position_id = proto.position.position_id if proto.position else None
        symbol_id = proto.order.trade_data.symbol_id if proto.order and proto.order.trade_data else 0

        # Extract deal details
        filled_volume = None
        fill_price = None
        timestamp = datetime.now(UTC)

        if proto.deal:
            filled_volume = proto.deal.filled_volume if proto.deal.filled_volume else None
            if proto.deal.execution_price:
                fill_price = Decimal(str(proto.deal.execution_price))
            if proto.deal.execution_timestamp:
                timestamp = self._timestamp_to_datetime(proto.deal.execution_timestamp)

        event = ExecutionEvent(
            account_id=proto.ctid_trader_account_id,
            execution_type=exec_type,
            order_id=order_id,
            position_id=position_id,
            symbol_id=symbol_id,
            side=side,
            filled_volume=filled_volume,
            fill_price=fill_price,
            timestamp=timestamp,
            is_server_event=proto.is_server_event if proto.is_server_event else False,
            error_code=proto.error_code if proto.error_code else None,
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
        await self._emitter.emit(event)

    async def _handle_trader_update(self, proto: ProtoOATraderUpdatedEvent) -> None:
        """Convert ProtoOATraderUpdatedEvent to TraderUpdateEvent."""
        trader = proto.trader
        if not trader:
            return

        event = TraderUpdateEvent(
            account_id=proto.ctid_trader_account_id,
            balance=trader.balance,
            leverage_in_cents=trader.leverage_in_cents if trader.leverage_in_cents else None,
            money_digits=trader.money_digits if trader.money_digits else 2,
        )
        await self._emitter.emit(event)

    async def _handle_margin_change(self, proto: ProtoOAMarginChangedEvent) -> None:
        """Convert ProtoOAMarginChangedEvent to MarginChangeEvent."""
        event = MarginChangeEvent(
            account_id=proto.ctid_trader_account_id,
            position_id=proto.position_id,
            used_margin=proto.used_margin,
            money_digits=proto.money_digits if proto.money_digits else 2,
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
        await self._emitter.emit(event)

    async def _handle_client_disconnect(
        self,
        proto: ProtoOAClientDisconnectEvent,
    ) -> None:
        """Convert ProtoOAClientDisconnectEvent to ClientDisconnectEvent."""
        event = ClientDisconnectEvent(
            reason=proto.reason or "Unknown",
        )
        await self._emitter.emit(event)

    async def _handle_account_disconnect(
        self,
        proto: ProtoOAAccountDisconnectEvent,
    ) -> None:
        """Convert ProtoOAAccountDisconnectEvent to AccountDisconnectEvent."""
        event = AccountDisconnectEvent(
            account_id=proto.ctid_trader_account_id,
        )
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
            timestamp=self._timestamp_to_datetime(proto.utc_last_update_timestamp),
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
        await self._emitter.emit(event)

    async def _handle_pnl_change(
        self,
        proto: ProtoOAv1PnLChangeEvent,
    ) -> None:
        """Convert ProtoOAv1PnLChangeEvent to PnLChangeEvent."""
        event = PnLChangeEvent(
            account_id=proto.ctid_trader_account_id,
            gross_unrealized_pnl=proto.gross_unrealized_pn_l,
            net_unrealized_pnl=proto.net_unrealized_pn_l,
            money_digits=proto.money_digits if proto.money_digits else 2,
        )
        await self._emitter.emit(event)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _timestamp_to_datetime(timestamp_ms: int) -> datetime:
        """Convert millisecond timestamp to datetime."""
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
