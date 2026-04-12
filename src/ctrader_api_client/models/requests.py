from __future__ import annotations

from datetime import datetime

from ctrader_api_client.enums import OrderSide, OrderType, StopTriggerMethod, TimeInForce

from .._internal.proto import (
    ProtoOAAmendOrderReq,
    ProtoOAAmendPositionSLTPReq,
    ProtoOAClosePositionReq,
    ProtoOANewOrderReq,
    ProtoOAOrderTriggerMethod,
    ProtoOAOrderType,
    ProtoOAPayloadType,
    ProtoOATimeInForce,
    ProtoOATradeSide,
)
from ._base import FrozenModel


# Reverse mappings for to_proto conversions

_ORDER_TYPE_TO_PROTO: dict[OrderType, int] = {
    OrderType.MARKET: ProtoOAOrderType.MARKET,
    OrderType.LIMIT: ProtoOAOrderType.LIMIT,
    OrderType.STOP: ProtoOAOrderType.STOP,
    OrderType.STOP_LOSS_TAKE_PROFIT: ProtoOAOrderType.STOP_LOSS_TAKE_PROFIT,
    OrderType.MARKET_RANGE: ProtoOAOrderType.MARKET_RANGE,
    OrderType.STOP_LIMIT: ProtoOAOrderType.STOP_LIMIT,
}

_TIME_IN_FORCE_TO_PROTO: dict[TimeInForce, int] = {
    TimeInForce.GOOD_TILL_DATE: ProtoOATimeInForce.GOOD_TILL_DATE,
    TimeInForce.GOOD_TILL_CANCEL: ProtoOATimeInForce.GOOD_TILL_CANCEL,
    TimeInForce.IMMEDIATE_OR_CANCEL: ProtoOATimeInForce.IMMEDIATE_OR_CANCEL,
    TimeInForce.FILL_OR_KILL: ProtoOATimeInForce.FILL_OR_KILL,
    TimeInForce.MARKET_ON_OPEN: ProtoOATimeInForce.MARKET_ON_OPEN,
}

_TRIGGER_TO_PROTO: dict[StopTriggerMethod, int] = {
    StopTriggerMethod.TRADE: ProtoOAOrderTriggerMethod.TRADE,
    StopTriggerMethod.OPPOSITE: ProtoOAOrderTriggerMethod.OPPOSITE,
    StopTriggerMethod.DOUBLE_TRADE: ProtoOAOrderTriggerMethod.DOUBLE_TRADE,
    StopTriggerMethod.DOUBLE_OPPOSITE: ProtoOAOrderTriggerMethod.DOUBLE_OPPOSITE,
}


class NewOrderRequest(FrozenModel):
    """Request to place a new order.

    Attributes:
        symbol_id: Symbol to trade.
        side: Order direction (BUY/SELL).
        volume: Volume in cents (100 = 0.01 lots).
        order_type: Type of order.
        limit_price: Limit price for LIMIT/STOP_LIMIT orders.
        stop_price: Stop trigger price for STOP/STOP_LIMIT orders.
        stop_loss: Stop loss price.
        take_profit: Take profit price.
        time_in_force: Order duration type.
        expiration_timestamp: Expiration for GTD orders.
        position_id: Position ID to close (for closing orders).
        client_order_id: User-defined order ID.
        label: User-defined label (max 100 chars).
        comment: User-defined comment (max 256 chars).
        base_slippage_price: Base price for slippage calculation.
        slippage_in_points: Max allowed slippage.
        trailing_stop_loss: Enable trailing stop loss.
        guaranteed_stop_loss: Enable guaranteed stop loss.
        relative_stop_loss: Stop loss distance in points.
        relative_take_profit: Take profit distance in points.
        stop_trigger_method: How to trigger stop orders.
    """

    symbol_id: int
    side: OrderSide
    volume: int
    order_type: OrderType = OrderType.MARKET

    # Prices (as float for convenience)
    limit_price: float | None = None
    stop_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None

    # Duration
    time_in_force: TimeInForce = TimeInForce.GOOD_TILL_CANCEL
    expiration_timestamp: datetime | None = None

    # Position reference
    position_id: int | None = None

    # Metadata
    client_order_id: str = ""
    label: str = ""
    comment: str = ""

    # Slippage
    base_slippage_price: float | None = None
    slippage_in_points: int | None = None

    # Relative SL/TP
    relative_stop_loss: int | None = None
    relative_take_profit: int | None = None

    # Flags
    trailing_stop_loss: bool = False
    guaranteed_stop_loss: bool = False
    stop_trigger_method: StopTriggerMethod | None = None

    def to_proto(self, account_id: int) -> ProtoOANewOrderReq:
        """Convert to proto message.

        Args:
            account_id: The trading account ID.

        Returns:
            Proto request message.
        """

        # Map enums to proto values
        order_type_value = ProtoOAOrderType(_ORDER_TYPE_TO_PROTO[self.order_type])
        trade_side_value = ProtoOATradeSide.BUY if self.side == OrderSide.BUY else ProtoOATradeSide.SELL
        time_in_force_value = ProtoOATimeInForce(_TIME_IN_FORCE_TO_PROTO[self.time_in_force])

        trigger_method = ProtoOAOrderTriggerMethod.TRADE
        if self.stop_trigger_method:
            trigger_method = ProtoOAOrderTriggerMethod(_TRIGGER_TO_PROTO[self.stop_trigger_method])

        return ProtoOANewOrderReq(
            payload_type=ProtoOAPayloadType.PROTO_OA_NEW_ORDER_REQ,
            ctid_trader_account_id=account_id,
            symbol_id=self.symbol_id,
            order_type=order_type_value,
            trade_side=trade_side_value,
            volume=self.volume,
            limit_price=self.limit_price or 0.0,
            stop_price=self.stop_price or 0.0,
            time_in_force=time_in_force_value,
            expiration_timestamp=int(self.expiration_timestamp.timestamp() * 1000) if self.expiration_timestamp else 0,
            stop_loss=self.stop_loss or 0.0,
            take_profit=self.take_profit or 0.0,
            comment=self.comment,
            base_slippage_price=self.base_slippage_price or 0.0,
            slippage_in_points=self.slippage_in_points or 0,
            label=self.label,
            position_id=self.position_id or 0,
            client_order_id=self.client_order_id,
            relative_stop_loss=self.relative_stop_loss or 0,
            relative_take_profit=self.relative_take_profit or 0,
            guaranteed_stop_loss=self.guaranteed_stop_loss,
            trailing_stop_loss=self.trailing_stop_loss,
            stop_trigger_method=trigger_method,
        )


class AmendOrderRequest(FrozenModel):
    """Request to modify a pending order.

    Only include fields you want to change.

    Attributes:
        order_id: The order to modify.
        volume: New volume in cents.
        limit_price: New limit price.
        stop_price: New stop trigger price.
        stop_loss: New stop loss price.
        take_profit: New take profit price.
        expiration_timestamp: New expiration time.
        slippage_in_points: New max slippage.
        trailing_stop_loss: Enable/disable trailing stop.
        guaranteed_stop_loss: Enable/disable guaranteed stop.
        relative_stop_loss: New relative stop loss in points.
        relative_take_profit: New relative take profit in points.
        stop_trigger_method: New trigger method.
    """

    order_id: int

    # Optional updates
    volume: int | None = None
    limit_price: float | None = None
    stop_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    expiration_timestamp: datetime | None = None
    slippage_in_points: int | None = None
    trailing_stop_loss: bool | None = None
    guaranteed_stop_loss: bool | None = None
    relative_stop_loss: int | None = None
    relative_take_profit: int | None = None
    stop_trigger_method: StopTriggerMethod | None = None

    def to_proto(self, account_id: int) -> ProtoOAAmendOrderReq:
        """Convert to proto message.

        Args:
            account_id: The trading account ID.

        Returns:
            Proto request message.
        """

        trigger_method = ProtoOAOrderTriggerMethod.TRADE
        if self.stop_trigger_method:
            trigger_method = ProtoOAOrderTriggerMethod(_TRIGGER_TO_PROTO[self.stop_trigger_method])

        return ProtoOAAmendOrderReq(
            payload_type=ProtoOAPayloadType.PROTO_OA_AMEND_ORDER_REQ,
            ctid_trader_account_id=account_id,
            order_id=self.order_id,
            volume=self.volume or 0,
            limit_price=self.limit_price or 0.0,
            stop_price=self.stop_price or 0.0,
            expiration_timestamp=int(self.expiration_timestamp.timestamp() * 1000) if self.expiration_timestamp else 0,
            stop_loss=self.stop_loss or 0.0,
            take_profit=self.take_profit or 0.0,
            slippage_in_points=self.slippage_in_points or 0,
            relative_stop_loss=self.relative_stop_loss or 0,
            relative_take_profit=self.relative_take_profit or 0,
            guaranteed_stop_loss=self.guaranteed_stop_loss if self.guaranteed_stop_loss is not None else False,
            trailing_stop_loss=self.trailing_stop_loss if self.trailing_stop_loss is not None else False,
            stop_trigger_method=trigger_method,
        )


class AmendPositionRequest(FrozenModel):
    """Request to modify a position's stop loss and take profit.

    Attributes:
        position_id: The position to modify.
        stop_loss: New stop loss price, or None to remove.
        take_profit: New take profit price, or None to remove.
        trailing_stop_loss: Enable/disable trailing stop.
        guaranteed_stop_loss: Enable/disable guaranteed stop.
        stop_loss_trigger_method: Trigger method for stop loss.
    """

    position_id: int
    stop_loss: float | None = None
    take_profit: float | None = None
    trailing_stop_loss: bool = False
    guaranteed_stop_loss: bool = False
    stop_loss_trigger_method: StopTriggerMethod | None = None

    def to_proto(self, account_id: int) -> ProtoOAAmendPositionSLTPReq:
        """Convert to proto message.

        Args:
            account_id: The trading account ID.

        Returns:
            Proto request message.
        """

        trigger_method = ProtoOAOrderTriggerMethod.TRADE
        if self.stop_loss_trigger_method:
            trigger_method = ProtoOAOrderTriggerMethod(_TRIGGER_TO_PROTO[self.stop_loss_trigger_method])

        return ProtoOAAmendPositionSLTPReq(
            payload_type=ProtoOAPayloadType.PROTO_OA_AMEND_POSITION_SLTP_REQ,
            ctid_trader_account_id=account_id,
            position_id=self.position_id,
            stop_loss=self.stop_loss or 0.0,
            take_profit=self.take_profit or 0.0,
            guaranteed_stop_loss=self.guaranteed_stop_loss,
            trailing_stop_loss=self.trailing_stop_loss,
            stop_loss_trigger_method=trigger_method,
        )


class ClosePositionRequest(FrozenModel):
    """Request to close a position.

    Attributes:
        position_id: The position to close.
        volume: Volume to close in cents. Use position's full volume
            for complete close, or partial volume for partial close.
    """

    position_id: int
    volume: int

    def to_proto(self, account_id: int) -> ProtoOAClosePositionReq:
        """Convert to proto message.

        Args:
            account_id: The trading account ID.

        Returns:
            Proto request message.
        """

        return ProtoOAClosePositionReq(
            payload_type=ProtoOAPayloadType.PROTO_OA_CLOSE_POSITION_REQ,
            ctid_trader_account_id=account_id,
            position_id=self.position_id,
            volume=self.volume,
        )
