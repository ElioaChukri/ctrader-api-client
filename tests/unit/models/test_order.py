"""Tests for order model."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from ctrader_api_client.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    StopTriggerMethod,
    TimeInForce,
)
from ctrader_api_client.models import Order


class TestOrderFromProto:
    """Tests for Order.from_proto method."""

    def test_from_proto_maps_all_fields(self) -> None:
        """Test that from_proto correctly maps all proto fields."""
        trade_data = MagicMock()
        trade_data.symbol_id = 1
        trade_data.volume = 100000
        trade_data.trade_side = 1  # BUY
        trade_data.open_timestamp = 1704067200000
        trade_data.label = "test_label"
        trade_data.comment = "test_comment"
        trade_data.guaranteed_stop_loss = True

        proto = MagicMock()
        proto.order_id = 12345
        proto.trade_data = trade_data
        proto.order_type = 2  # LIMIT
        proto.order_status = 1  # ACCEPTED
        proto.time_in_force = 2  # GOOD_TILL_CANCEL
        proto.limit_price = 1.12000
        proto.stop_price = 0
        proto.stop_loss = 1.11000
        proto.take_profit = 1.15000
        proto.execution_price = 0
        proto.executed_volume = 0
        proto.expiration_timestamp = 1704153600000
        proto.position_id = 54321
        proto.base_slippage_price = 1.12100
        proto.slippage_in_points = 5
        proto.relative_stop_loss = 100
        proto.relative_take_profit = 300
        proto.closing_order = False
        proto.is_stop_out = False
        proto.trailing_stop_loss = True
        proto.stop_trigger_method = 2  # OPPOSITE
        proto.client_order_id = "client123"
        proto.utc_last_update_timestamp = 1704153600000

        order = Order.from_proto(proto)

        assert order.order_id == 12345
        assert order.symbol_id == 1
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.status == OrderStatus.ACCEPTED
        assert order.volume == 100000
        assert order.time_in_force == TimeInForce.GOOD_TILL_CANCEL
        assert order.limit_price == 1.12000
        assert order.stop_price is None
        assert order.stop_loss == 1.11000
        assert order.take_profit == 1.15000
        assert order.execution_price is None
        assert order.executed_volume == 0
        assert order.expiration_timestamp == datetime(2024, 1, 2, 0, 0, 0, tzinfo=UTC)
        assert order.position_id == 54321
        assert order.base_slippage_price == 1.12100
        assert order.slippage_in_points == 5
        assert order.relative_stop_loss == 100
        assert order.relative_take_profit == 300
        assert order.is_closing_order is False
        assert order.is_stop_out is False
        assert order.trailing_stop_loss is True
        assert order.guaranteed_stop_loss is True
        assert order.stop_trigger_method == StopTriggerMethod.OPPOSITE
        assert order.client_order_id == "client123"
        assert order.label == "test_label"
        assert order.comment == "test_comment"

    def test_from_proto_maps_order_types(self) -> None:
        """Test that all order types are correctly mapped."""
        trade_data = MagicMock()
        trade_data.symbol_id = 1
        trade_data.volume = 100000
        trade_data.trade_side = 1
        trade_data.open_timestamp = 1704067200000
        trade_data.label = ""
        trade_data.comment = ""
        trade_data.guaranteed_stop_loss = False

        proto = MagicMock()
        proto.order_id = 1
        proto.trade_data = trade_data
        proto.order_status = 1
        proto.time_in_force = 2
        proto.limit_price = 0
        proto.stop_price = 0
        proto.stop_loss = 0
        proto.take_profit = 0
        proto.execution_price = 0
        proto.executed_volume = 0
        proto.expiration_timestamp = 0
        proto.position_id = 0
        proto.base_slippage_price = 0
        proto.slippage_in_points = 0
        proto.relative_stop_loss = 0
        proto.relative_take_profit = 0
        proto.closing_order = False
        proto.is_stop_out = False
        proto.trailing_stop_loss = False
        proto.stop_trigger_method = 1
        proto.client_order_id = ""
        proto.utc_last_update_timestamp = 0

        test_cases = [
            (1, OrderType.MARKET),
            (2, OrderType.LIMIT),
            (3, OrderType.STOP),
            (4, OrderType.STOP_LOSS_TAKE_PROFIT),
            (5, OrderType.MARKET_RANGE),
            (6, OrderType.STOP_LIMIT),
        ]

        for proto_value, expected_type in test_cases:
            proto.order_type = proto_value
            order = Order.from_proto(proto)
            assert order.order_type == expected_type

    def test_from_proto_maps_order_statuses(self) -> None:
        """Test that all order statuses are correctly mapped."""
        trade_data = MagicMock()
        trade_data.symbol_id = 1
        trade_data.volume = 100000
        trade_data.trade_side = 1
        trade_data.open_timestamp = 1704067200000
        trade_data.label = ""
        trade_data.comment = ""
        trade_data.guaranteed_stop_loss = False

        proto = MagicMock()
        proto.order_id = 1
        proto.trade_data = trade_data
        proto.order_type = 1
        proto.time_in_force = 2
        proto.limit_price = 0
        proto.stop_price = 0
        proto.stop_loss = 0
        proto.take_profit = 0
        proto.execution_price = 0
        proto.executed_volume = 0
        proto.expiration_timestamp = 0
        proto.position_id = 0
        proto.base_slippage_price = 0
        proto.slippage_in_points = 0
        proto.relative_stop_loss = 0
        proto.relative_take_profit = 0
        proto.closing_order = False
        proto.is_stop_out = False
        proto.trailing_stop_loss = False
        proto.stop_trigger_method = 1
        proto.client_order_id = ""
        proto.utc_last_update_timestamp = 0

        test_cases = [
            (1, OrderStatus.ACCEPTED),
            (2, OrderStatus.FILLED),
            (3, OrderStatus.REJECTED),
            (4, OrderStatus.EXPIRED),
            (5, OrderStatus.CANCELLED),
        ]

        for proto_value, expected_status in test_cases:
            proto.order_status = proto_value
            order = Order.from_proto(proto)
            assert order.status == expected_status

    def test_from_proto_maps_time_in_force(self) -> None:
        """Test that all time in force values are correctly mapped."""
        trade_data = MagicMock()
        trade_data.symbol_id = 1
        trade_data.volume = 100000
        trade_data.trade_side = 1
        trade_data.open_timestamp = 1704067200000
        trade_data.label = ""
        trade_data.comment = ""
        trade_data.guaranteed_stop_loss = False

        proto = MagicMock()
        proto.order_id = 1
        proto.trade_data = trade_data
        proto.order_type = 1
        proto.order_status = 1
        proto.limit_price = 0
        proto.stop_price = 0
        proto.stop_loss = 0
        proto.take_profit = 0
        proto.execution_price = 0
        proto.executed_volume = 0
        proto.expiration_timestamp = 0
        proto.position_id = 0
        proto.base_slippage_price = 0
        proto.slippage_in_points = 0
        proto.relative_stop_loss = 0
        proto.relative_take_profit = 0
        proto.closing_order = False
        proto.is_stop_out = False
        proto.trailing_stop_loss = False
        proto.stop_trigger_method = 1
        proto.client_order_id = ""
        proto.utc_last_update_timestamp = 0

        test_cases = [
            (1, TimeInForce.GOOD_TILL_DATE),
            (2, TimeInForce.GOOD_TILL_CANCEL),
            (3, TimeInForce.IMMEDIATE_OR_CANCEL),
            (4, TimeInForce.FILL_OR_KILL),
            (5, TimeInForce.MARKET_ON_OPEN),
        ]

        for proto_value, expected_tif in test_cases:
            proto.time_in_force = proto_value
            order = Order.from_proto(proto)
            assert order.time_in_force == expected_tif


class TestOrderProperties:
    """Tests for Order computed properties."""

    def test_is_pending_true_when_accepted(self) -> None:
        """Test is_pending returns True when status is ACCEPTED."""
        order = Order(
            order_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            status=OrderStatus.ACCEPTED,
            volume=100000,
            time_in_force=TimeInForce.GOOD_TILL_CANCEL,
            open_timestamp=datetime.now(UTC),
        )

        assert order.is_pending is True

    def test_is_pending_false_when_filled(self) -> None:
        """Test is_pending returns False when status is FILLED."""
        order = Order(
            order_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            volume=100000,
            time_in_force=TimeInForce.GOOD_TILL_CANCEL,
            open_timestamp=datetime.now(UTC),
        )

        assert order.is_pending is False

    def test_is_pending_false_when_cancelled(self) -> None:
        """Test is_pending returns False when status is CANCELLED."""
        order = Order(
            order_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            status=OrderStatus.CANCELLED,
            volume=100000,
            time_in_force=TimeInForce.GOOD_TILL_CANCEL,
            open_timestamp=datetime.now(UTC),
        )

        assert order.is_pending is False

    def test_is_filled_true_when_filled(self) -> None:
        """Test is_filled returns True when status is FILLED."""
        order = Order(
            order_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            volume=100000,
            time_in_force=TimeInForce.GOOD_TILL_CANCEL,
            open_timestamp=datetime.now(UTC),
        )

        assert order.is_filled is True

    def test_is_filled_false_when_accepted(self) -> None:
        """Test is_filled returns False when status is ACCEPTED."""
        order = Order(
            order_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            status=OrderStatus.ACCEPTED,
            volume=100000,
            time_in_force=TimeInForce.GOOD_TILL_CANCEL,
            open_timestamp=datetime.now(UTC),
        )

        assert order.is_filled is False
