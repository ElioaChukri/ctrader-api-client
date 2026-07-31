"""How user-facing request models translate into wire messages."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ctrader_api_client._internal.proto import (
    ProtoOAOrderTriggerMethod,
    ProtoOAOrderType,
    ProtoOATimeInForce,
    ProtoOATradeSide,
)
from ctrader_api_client.enums import OrderSide, OrderType, StopTriggerMethod, TimeInForce
from ctrader_api_client.models import (
    AmendOrderRequest,
    AmendPositionRequest,
    ClosePositionRequest,
    NewOrderRequest,
)


ACCOUNT_ID = 12345678


def test_a_market_order_carries_symbol_side_and_volume() -> None:
    proto = NewOrderRequest(symbol_id=270, side=OrderSide.BUY, volume=100_000).to_proto(ACCOUNT_ID)

    assert proto.ctid_trader_account_id == ACCOUNT_ID
    assert proto.symbol_id == 270
    assert proto.volume == 100_000
    assert proto.trade_side == ProtoOATradeSide.BUY
    assert proto.order_type == ProtoOAOrderType.MARKET


@pytest.mark.parametrize(
    ("side", "expected"),
    [(OrderSide.BUY, ProtoOATradeSide.BUY), (OrderSide.SELL, ProtoOATradeSide.SELL)],
)
def test_the_order_side_is_translated(side: OrderSide, expected: ProtoOATradeSide) -> None:
    proto = NewOrderRequest(symbol_id=1, side=side, volume=1).to_proto(ACCOUNT_ID)

    assert proto.trade_side == expected


@pytest.mark.parametrize(
    ("order_type", "expected"),
    [
        (OrderType.MARKET, ProtoOAOrderType.MARKET),
        (OrderType.LIMIT, ProtoOAOrderType.LIMIT),
        (OrderType.STOP, ProtoOAOrderType.STOP),
        (OrderType.STOP_LIMIT, ProtoOAOrderType.STOP_LIMIT),
        (OrderType.MARKET_RANGE, ProtoOAOrderType.MARKET_RANGE),
    ],
)
def test_the_order_type_is_translated(order_type: OrderType, expected: ProtoOAOrderType) -> None:
    proto = NewOrderRequest(symbol_id=1, side=OrderSide.BUY, volume=1, order_type=order_type).to_proto(ACCOUNT_ID)

    assert proto.order_type == expected


@pytest.mark.parametrize(
    ("time_in_force", "expected"),
    [
        (TimeInForce.GOOD_TILL_CANCEL, ProtoOATimeInForce.GOOD_TILL_CANCEL),
        (TimeInForce.IMMEDIATE_OR_CANCEL, ProtoOATimeInForce.IMMEDIATE_OR_CANCEL),
        (TimeInForce.FILL_OR_KILL, ProtoOATimeInForce.FILL_OR_KILL),
        (TimeInForce.GOOD_TILL_DATE, ProtoOATimeInForce.GOOD_TILL_DATE),
    ],
)
def test_the_duration_is_translated(time_in_force: TimeInForce, expected: ProtoOATimeInForce) -> None:
    proto = NewOrderRequest(
        symbol_id=1,
        side=OrderSide.BUY,
        volume=1,
        time_in_force=time_in_force,
    ).to_proto(ACCOUNT_ID)

    assert proto.time_in_force == expected


def test_order_prices_are_sent_as_prices() -> None:
    proto = NewOrderRequest(
        symbol_id=1,
        side=OrderSide.BUY,
        volume=1,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("1.10500"),
        stop_price=Decimal("1.09000"),
        stop_loss=Decimal("1.08000"),
        take_profit=Decimal("1.12000"),
    ).to_proto(ACCOUNT_ID)

    assert proto.limit_price == pytest.approx(1.105)
    assert proto.stop_price == pytest.approx(1.09)
    assert proto.stop_loss == pytest.approx(1.08)
    assert proto.take_profit == pytest.approx(1.12)


def test_relative_distances_are_sent_in_scaled_points() -> None:
    """Absolute prices go over as floats, but relative distances are scaled integers."""
    proto = NewOrderRequest(
        symbol_id=1,
        side=OrderSide.BUY,
        volume=1,
        relative_stop_loss=Decimal("0.00150"),
        relative_take_profit=Decimal("0.00300"),
    ).to_proto(ACCOUNT_ID)

    assert proto.relative_stop_loss == 150
    assert proto.relative_take_profit == 300


def test_an_expiry_is_sent_in_milliseconds() -> None:
    expiry = datetime(2030, 1, 1, tzinfo=UTC)

    proto = NewOrderRequest(
        symbol_id=1,
        side=OrderSide.BUY,
        volume=1,
        time_in_force=TimeInForce.GOOD_TILL_DATE,
        expiration_timestamp=expiry,
    ).to_proto(ACCOUNT_ID)

    assert proto.expiration_timestamp == int(expiry.timestamp() * 1000)


def test_order_metadata_is_forwarded() -> None:
    proto = NewOrderRequest(
        symbol_id=1,
        side=OrderSide.BUY,
        volume=1,
        label="strategy-a",
        comment="entry signal",
        client_order_id="abc-123",
    ).to_proto(ACCOUNT_ID)

    assert (proto.label, proto.comment, proto.client_order_id) == ("strategy-a", "entry signal", "abc-123")


def test_unset_order_prices_are_sent_as_zero() -> None:
    """The API treats zero as "not specified"; sending anything else would set a real level."""
    proto = NewOrderRequest(symbol_id=1, side=OrderSide.BUY, volume=1).to_proto(ACCOUNT_ID)

    assert (proto.limit_price, proto.stop_price, proto.stop_loss, proto.take_profit) == (0.0, 0.0, 0.0, 0.0)
    assert (proto.position_id, proto.slippage_in_points, proto.expiration_timestamp) == (0, 0, 0)


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        (StopTriggerMethod.TRADE, ProtoOAOrderTriggerMethod.TRADE),
        (StopTriggerMethod.OPPOSITE, ProtoOAOrderTriggerMethod.OPPOSITE),
        (StopTriggerMethod.DOUBLE_TRADE, ProtoOAOrderTriggerMethod.DOUBLE_TRADE),
        (StopTriggerMethod.DOUBLE_OPPOSITE, ProtoOAOrderTriggerMethod.DOUBLE_OPPOSITE),
    ],
)
def test_the_stop_trigger_method_is_translated(
    method: StopTriggerMethod,
    expected: ProtoOAOrderTriggerMethod,
) -> None:
    proto = NewOrderRequest(
        symbol_id=1,
        side=OrderSide.BUY,
        volume=1,
        stop_trigger_method=method,
    ).to_proto(ACCOUNT_ID)

    assert proto.stop_trigger_method == expected


def test_an_amendment_identifies_the_order_and_the_new_levels() -> None:
    proto = AmendOrderRequest(
        order_id=555,
        volume=50_000,
        limit_price=Decimal("1.2"),
        stop_loss=Decimal("1.1"),
    ).to_proto(ACCOUNT_ID)

    assert proto.ctid_trader_account_id == ACCOUNT_ID
    assert proto.order_id == 555
    assert proto.volume == 50_000
    assert proto.limit_price == pytest.approx(1.2)
    assert proto.stop_loss == pytest.approx(1.1)


def test_an_amendment_clears_levels_left_unset() -> None:
    """Amend replaces the whole order, so omitted fields must go over as cleared."""
    proto = AmendOrderRequest(order_id=555).to_proto(ACCOUNT_ID)

    assert (proto.volume, proto.stop_loss, proto.take_profit, proto.limit_price) == (0, 0.0, 0.0, 0.0)
    assert proto.trailing_stop_loss is False
    assert proto.guaranteed_stop_loss is False


def test_a_position_amendment_carries_its_protective_levels() -> None:
    proto = AmendPositionRequest(
        position_id=777,
        stop_loss=Decimal("1.05"),
        take_profit=Decimal("1.25"),
        trailing_stop_loss=True,
    ).to_proto(ACCOUNT_ID)

    assert proto.position_id == 777
    assert proto.stop_loss == pytest.approx(1.05)
    assert proto.take_profit == pytest.approx(1.25)
    assert proto.trailing_stop_loss is True


def test_a_position_amendment_defaults_to_the_trade_trigger() -> None:
    proto = AmendPositionRequest(position_id=777).to_proto(ACCOUNT_ID)

    assert proto.stop_loss_trigger_method == ProtoOAOrderTriggerMethod.TRADE


def test_a_close_request_names_the_position_and_the_volume() -> None:
    proto = ClosePositionRequest(position_id=777, volume=25_000).to_proto(ACCOUNT_ID)

    assert (proto.ctid_trader_account_id, proto.position_id, proto.volume) == (ACCOUNT_ID, 777, 25_000)
