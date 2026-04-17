from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .._internal.proto import ProtoOAOrderStatus, ProtoOAOrderTriggerMethod, ProtoOAOrderType, ProtoOATimeInForce
from ..enums import OrderSide, OrderStatus, OrderType, StopTriggerMethod, TimeInForce
from ._base import FrozenModel


if TYPE_CHECKING:
    from .._internal.proto import ProtoOAOrder


def _timestamp_to_datetime(timestamp_ms: int) -> datetime:
    """Convert millisecond timestamp to datetime."""
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)


_ORDER_TYPE_MAP: dict[int, OrderType] = {
    ProtoOAOrderType.MARKET: OrderType.MARKET,
    ProtoOAOrderType.LIMIT: OrderType.LIMIT,
    ProtoOAOrderType.STOP: OrderType.STOP,
    ProtoOAOrderType.STOP_LOSS_TAKE_PROFIT: OrderType.STOP_LOSS_TAKE_PROFIT,
    ProtoOAOrderType.MARKET_RANGE: OrderType.MARKET_RANGE,
    ProtoOAOrderType.STOP_LIMIT: OrderType.STOP_LIMIT,
}

_ORDER_STATUS_MAP: dict[int, OrderStatus] = {
    ProtoOAOrderStatus.ORDER_STATUS_ACCEPTED: OrderStatus.ACCEPTED,
    ProtoOAOrderStatus.ORDER_STATUS_FILLED: OrderStatus.FILLED,
    ProtoOAOrderStatus.ORDER_STATUS_REJECTED: OrderStatus.REJECTED,
    ProtoOAOrderStatus.ORDER_STATUS_EXPIRED: OrderStatus.EXPIRED,
    ProtoOAOrderStatus.ORDER_STATUS_CANCELLED: OrderStatus.CANCELLED,
}

_TIME_IN_FORCE_MAP: dict[int, TimeInForce] = {
    ProtoOATimeInForce.GOOD_TILL_DATE: TimeInForce.GOOD_TILL_DATE,
    ProtoOATimeInForce.GOOD_TILL_CANCEL: TimeInForce.GOOD_TILL_CANCEL,
    ProtoOATimeInForce.IMMEDIATE_OR_CANCEL: TimeInForce.IMMEDIATE_OR_CANCEL,
    ProtoOATimeInForce.FILL_OR_KILL: TimeInForce.FILL_OR_KILL,
    ProtoOATimeInForce.MARKET_ON_OPEN: TimeInForce.MARKET_ON_OPEN,
}

_TRIGGER_METHOD_MAP: dict[int, StopTriggerMethod] = {
    ProtoOAOrderTriggerMethod.TRADE: StopTriggerMethod.TRADE,
    ProtoOAOrderTriggerMethod.OPPOSITE: StopTriggerMethod.OPPOSITE,
    ProtoOAOrderTriggerMethod.DOUBLE_TRADE: StopTriggerMethod.DOUBLE_TRADE,
    ProtoOAOrderTriggerMethod.DOUBLE_OPPOSITE: StopTriggerMethod.DOUBLE_OPPOSITE,
}


class Order(FrozenModel):
    """A trading order (pending or historical).

    Represents an order with all details including type, prices, volume,
    and execution information.

    Attributes:
        order_id: Unique order identifier.
        symbol_id: The symbol being traded.
        side: Order direction (BUY/SELL).
        order_type: Type of order (MARKET, LIMIT, STOP, etc.).
        status: Current order status.
        volume: Order volume in cents.
        time_in_force: Order duration type.
        open_timestamp: When the order was created.
        limit_price: Limit price as float, or None.
        stop_price: Stop trigger price as float, or None.
        stop_loss: Stop loss price as float, or None.
        take_profit: Take profit price as float, or None.
        execution_price: Average fill price as float, or None.
        executed_volume: Volume that has been filled, in cents.
        expiration_timestamp: When the order expires, or None.
        position_id: Associated position ID, or None.
        base_slippage_price: Base price for slippage calculation.
        slippage_in_points: Max allowed slippage in points.
        relative_stop_loss: Stop loss distance in points.
        relative_take_profit: Take profit distance in points.
        is_closing_order: Whether this order closes a position.
        is_stop_out: Whether this order was triggered by stop-out.
        trailing_stop_loss: Whether trailing stop is enabled.
        guaranteed_stop_loss: Whether guaranteed stop loss is enabled.
        stop_trigger_method: Method for triggering stop orders.
        client_order_id: User-defined order ID.
        label: User-defined label.
        comment: User-defined comment.
        last_update_timestamp: When the order was last modified.
    """

    order_id: int
    symbol_id: int
    side: OrderSide
    order_type: OrderType
    status: OrderStatus
    volume: int
    time_in_force: TimeInForce
    open_timestamp: datetime

    # Prices (as float from API)
    limit_price: float | None = None
    stop_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    execution_price: float | None = None

    # Execution
    executed_volume: int = 0
    expiration_timestamp: datetime | None = None
    position_id: int | None = None

    # Slippage
    base_slippage_price: float | None = None
    slippage_in_points: int | None = None

    # Relative SL/TP (in points)
    relative_stop_loss: int | None = None
    relative_take_profit: int | None = None

    # Flags
    is_closing_order: bool = False
    is_stop_out: bool = False
    trailing_stop_loss: bool = False
    guaranteed_stop_loss: bool = False
    stop_trigger_method: StopTriggerMethod = StopTriggerMethod.TRADE

    # Metadata
    client_order_id: str = ""
    label: str = ""
    comment: str = ""
    last_update_timestamp: datetime | None = None

    @property
    def is_pending(self) -> bool:
        """Whether this is a pending order."""
        return self.status == OrderStatus.ACCEPTED

    @property
    def is_filled(self) -> bool:
        """Whether this order has been fully filled."""
        return self.status == OrderStatus.FILLED

    @classmethod
    def from_proto(cls, proto: ProtoOAOrder) -> Order:
        """Create Order from proto message.

        Args:
            proto: The proto message to convert.

        Returns:
            A new Order instance.
        """
        trade_data = proto.trade_data

        # Determine side from trade_data
        side = OrderSide.BUY
        if trade_data and trade_data.trade_side == 2:
            side = OrderSide.SELL

        # Get open timestamp
        open_ts = datetime.now(UTC)
        if trade_data and trade_data.open_timestamp:
            open_ts = _timestamp_to_datetime(trade_data.open_timestamp)

        return cls(
            order_id=proto.order_id,
            symbol_id=trade_data.symbol_id if trade_data else 0,
            side=side,
            order_type=_ORDER_TYPE_MAP.get(proto.order_type, OrderType.MARKET),
            status=_ORDER_STATUS_MAP.get(proto.order_status, OrderStatus.ACCEPTED),
            volume=trade_data.volume if trade_data else 0,
            time_in_force=_TIME_IN_FORCE_MAP.get(proto.time_in_force, TimeInForce.GOOD_TILL_CANCEL),
            open_timestamp=open_ts,
            limit_price=proto.limit_price if proto.limit_price else None,
            stop_price=proto.stop_price if proto.stop_price else None,
            stop_loss=proto.stop_loss if proto.stop_loss else None,
            take_profit=proto.take_profit if proto.take_profit else None,
            execution_price=proto.execution_price if proto.execution_price else None,
            executed_volume=proto.executed_volume if proto.executed_volume else 0,
            expiration_timestamp=(
                _timestamp_to_datetime(proto.expiration_timestamp) if proto.expiration_timestamp else None
            ),
            position_id=proto.position_id if proto.position_id else None,
            base_slippage_price=proto.base_slippage_price if proto.base_slippage_price else None,
            slippage_in_points=proto.slippage_in_points if proto.slippage_in_points else None,
            relative_stop_loss=proto.relative_stop_loss if proto.relative_stop_loss else None,
            relative_take_profit=proto.relative_take_profit if proto.relative_take_profit else None,
            is_closing_order=proto.closing_order,
            is_stop_out=proto.is_stop_out,
            trailing_stop_loss=proto.trailing_stop_loss,
            guaranteed_stop_loss=trade_data.guaranteed_stop_loss if trade_data else False,
            stop_trigger_method=_TRIGGER_METHOD_MAP.get(proto.stop_trigger_method, StopTriggerMethod.TRADE),
            client_order_id=proto.client_order_id or "",
            label=trade_data.label if trade_data else "",
            comment=trade_data.comment if trade_data else "",
            last_update_timestamp=(
                _timestamp_to_datetime(proto.utc_last_update_timestamp) if proto.utc_last_update_timestamp else None
            ),
        )
