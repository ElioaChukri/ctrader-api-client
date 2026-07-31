"""Shared conversion from ProtoOAExecutionEvent to the typed ExecutionEvent.

Both a trade request's reply and a server-pushed execution arrive as a
ProtoOAExecutionEvent, so the API layer and the event router need the same
conversion. They differ only in what they do about an execution type the client
does not recognise — the API layer fails the call, the router drops the event —
which is why this returns None instead of picking one of those for them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import betterproto

from .._internal import timestamp_to_datetime
from .._internal.proto import ProtoOAExecutionEvent, ProtoOAExecutionType, ProtoOATradeSide
from ..enums import ExecutionType, OrderSide
from .types import ExecutionEvent


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


def execution_event_from_proto(proto: ProtoOAExecutionEvent) -> ExecutionEvent | None:
    """Convert a ProtoOAExecutionEvent to an ExecutionEvent.

    Args:
        proto: The proto message to convert.

    Returns:
        The converted event, or None if the execution type is one this client
        does not recognise. Callers decide whether that is an error or an event
        to skip.
    """
    exec_type = _EXECUTION_TYPE_MAP.get(proto.execution_type)
    if exec_type is None:
        return None

    # An absent sub-message parses into a default instance, so presence has to
    # be read from the wire rather than from truthiness.
    has_order = betterproto.serialized_on_wire(proto.order)
    has_position = betterproto.serialized_on_wire(proto.position)
    has_deal = betterproto.serialized_on_wire(proto.deal)

    side = OrderSide.BUY
    if has_order and proto.order.trade_data.trade_side == ProtoOATradeSide.SELL:
        side = OrderSide.SELL

    order_id = proto.order.order_id if has_order else 0
    position_id = proto.position.position_id if has_position else None
    symbol_id = proto.order.trade_data.symbol_id if has_order else 0

    # Extract deal details
    filled_volume = None
    fill_price = None
    timestamp = datetime.now(UTC)

    if has_deal:
        filled_volume = proto.deal.filled_volume if proto.deal.filled_volume else None
        if proto.deal.execution_price:
            fill_price = Decimal(str(proto.deal.execution_price))
        if proto.deal.execution_timestamp:
            timestamp = timestamp_to_datetime(proto.deal.execution_timestamp)

    return ExecutionEvent(
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
