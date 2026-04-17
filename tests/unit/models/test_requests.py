"""Tests for request models."""

from __future__ import annotations

from datetime import UTC, datetime

from ctrader_api_client.enums import OrderSide, OrderType, StopTriggerMethod, TimeInForce
from ctrader_api_client.models import (
    AmendOrderRequest,
    AmendPositionRequest,
    ClosePositionRequest,
    NewOrderRequest,
)


class TestNewOrderRequestToProto:
    """Tests for NewOrderRequest.to_proto method."""

    def test_to_proto_market_order(self) -> None:
        """Test to_proto for a basic market order."""
        request = NewOrderRequest(
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            order_type=OrderType.MARKET,
        )

        proto = request.to_proto(account_id=12345)

        assert proto.ctid_trader_account_id == 12345
        assert proto.symbol_id == 1
        assert proto.volume == 100000
        assert proto.order_type.value == 1  # MARKET
        assert proto.trade_side.value == 1  # BUY

    def test_to_proto_limit_order(self) -> None:
        """Test to_proto for a limit order."""
        request = NewOrderRequest(
            symbol_id=1,
            side=OrderSide.SELL,
            volume=50000,
            order_type=OrderType.LIMIT,
            limit_price=1.12500,
        )

        proto = request.to_proto(account_id=12345)

        assert proto.order_type.value == 2  # LIMIT
        assert proto.trade_side.value == 2  # SELL
        assert proto.limit_price == 1.12500

    def test_to_proto_stop_order(self) -> None:
        """Test to_proto for a stop order."""
        request = NewOrderRequest(
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            order_type=OrderType.STOP,
            stop_price=1.13000,
        )

        proto = request.to_proto(account_id=12345)

        assert proto.order_type.value == 3  # STOP
        assert proto.stop_price == 1.13000

    def test_to_proto_with_sl_tp(self) -> None:
        """Test to_proto with stop loss and take profit."""
        request = NewOrderRequest(
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            order_type=OrderType.MARKET,
            stop_loss=1.11000,
            take_profit=1.15000,
        )

        proto = request.to_proto(account_id=12345)

        assert proto.stop_loss == 1.11000
        assert proto.take_profit == 1.15000

    def test_to_proto_with_time_in_force(self) -> None:
        """Test to_proto with various time in force values."""
        test_cases = [
            (TimeInForce.GOOD_TILL_CANCEL, 2),
            (TimeInForce.GOOD_TILL_DATE, 1),
            (TimeInForce.IMMEDIATE_OR_CANCEL, 3),
            (TimeInForce.FILL_OR_KILL, 4),
            (TimeInForce.MARKET_ON_OPEN, 5),
        ]

        for tif, expected_value in test_cases:
            request = NewOrderRequest(
                symbol_id=1,
                side=OrderSide.BUY,
                volume=100000,
                order_type=OrderType.LIMIT,
                limit_price=1.12000,
                time_in_force=tif,
            )

            proto = request.to_proto(account_id=12345)
            assert proto.time_in_force.value == expected_value

    def test_to_proto_with_expiration(self) -> None:
        """Test to_proto with expiration timestamp."""
        expiration = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        request = NewOrderRequest(
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            order_type=OrderType.LIMIT,
            limit_price=1.12000,
            time_in_force=TimeInForce.GOOD_TILL_DATE,
            expiration_timestamp=expiration,
        )

        proto = request.to_proto(account_id=12345)

        # 1704110400000 ms = 2024-01-01 12:00:00 UTC
        assert proto.expiration_timestamp == 1704110400000

    def test_to_proto_with_metadata(self) -> None:
        """Test to_proto with label, comment, and client_order_id."""
        request = NewOrderRequest(
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            order_type=OrderType.MARKET,
            label="my_strategy",
            comment="Entry signal",
            client_order_id="order_123",
        )

        proto = request.to_proto(account_id=12345)

        assert proto.label == "my_strategy"
        assert proto.comment == "Entry signal"
        assert proto.client_order_id == "order_123"

    def test_to_proto_with_slippage(self) -> None:
        """Test to_proto with slippage settings."""
        request = NewOrderRequest(
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            order_type=OrderType.MARKET_RANGE,
            base_slippage_price=1.12000,
            slippage_in_points=10,
        )

        proto = request.to_proto(account_id=12345)

        assert proto.base_slippage_price == 1.12000
        assert proto.slippage_in_points == 10

    def test_to_proto_with_relative_sl_tp(self) -> None:
        """Test to_proto with relative stop loss and take profit."""
        request = NewOrderRequest(
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            order_type=OrderType.MARKET,
            relative_stop_loss=0.0005,  # 5 pips in price units
            relative_take_profit=0.001,  # 10 pips in price units
        )

        proto = request.to_proto(account_id=12345)

        # Values are multiplied by 1e5 for the proto
        assert proto.relative_stop_loss == 50
        assert proto.relative_take_profit == 100

    def test_to_proto_with_trailing_stop(self) -> None:
        """Test to_proto with trailing stop loss."""
        request = NewOrderRequest(
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            order_type=OrderType.MARKET,
            stop_loss=1.11000,
            trailing_stop_loss=True,
        )

        proto = request.to_proto(account_id=12345)

        assert proto.trailing_stop_loss is True

    def test_to_proto_with_guaranteed_stop(self) -> None:
        """Test to_proto with guaranteed stop loss."""
        request = NewOrderRequest(
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            order_type=OrderType.MARKET,
            stop_loss=1.11000,
            guaranteed_stop_loss=True,
        )

        proto = request.to_proto(account_id=12345)

        assert proto.guaranteed_stop_loss is True

    def test_to_proto_with_stop_trigger_method(self) -> None:
        """Test to_proto with stop trigger method."""
        test_cases = [
            (StopTriggerMethod.TRADE, 1),
            (StopTriggerMethod.OPPOSITE, 2),
            (StopTriggerMethod.DOUBLE_TRADE, 3),
            (StopTriggerMethod.DOUBLE_OPPOSITE, 4),
        ]

        for method, expected_value in test_cases:
            request = NewOrderRequest(
                symbol_id=1,
                side=OrderSide.BUY,
                volume=100000,
                order_type=OrderType.STOP,
                stop_price=1.13000,
                stop_trigger_method=method,
            )

            proto = request.to_proto(account_id=12345)
            assert proto.stop_trigger_method.value == expected_value

    def test_to_proto_closing_order(self) -> None:
        """Test to_proto for a closing order."""
        request = NewOrderRequest(
            symbol_id=1,
            side=OrderSide.SELL,
            volume=100000,
            order_type=OrderType.MARKET,
            position_id=54321,
        )

        proto = request.to_proto(account_id=12345)

        assert proto.position_id == 54321


class TestAmendOrderRequestToProto:
    """Tests for AmendOrderRequest.to_proto method."""

    def test_to_proto_basic(self) -> None:
        """Test to_proto with basic fields."""
        request = AmendOrderRequest(
            order_id=12345,
            volume=50000,
            limit_price=1.13000,
        )

        proto = request.to_proto(account_id=11111)

        assert proto.ctid_trader_account_id == 11111
        assert proto.order_id == 12345
        assert proto.volume == 50000
        assert proto.limit_price == 1.13000

    def test_to_proto_with_sl_tp(self) -> None:
        """Test to_proto with stop loss and take profit update."""
        request = AmendOrderRequest(
            order_id=12345,
            stop_loss=1.11000,
            take_profit=1.16000,
        )

        proto = request.to_proto(account_id=11111)

        assert proto.stop_loss == 1.11000
        assert proto.take_profit == 1.16000

    def test_to_proto_with_expiration(self) -> None:
        """Test to_proto with new expiration."""
        expiration = datetime(2024, 1, 15, 0, 0, 0, tzinfo=UTC)
        request = AmendOrderRequest(
            order_id=12345,
            expiration_timestamp=expiration,
        )

        proto = request.to_proto(account_id=11111)

        # 1705276800000 ms = 2024-01-15 00:00:00 UTC
        assert proto.expiration_timestamp == 1705276800000

    def test_to_proto_with_trailing_stop(self) -> None:
        """Test to_proto enabling trailing stop."""
        request = AmendOrderRequest(
            order_id=12345,
            trailing_stop_loss=True,
        )

        proto = request.to_proto(account_id=11111)

        assert proto.trailing_stop_loss is True


class TestAmendPositionRequestToProto:
    """Tests for AmendPositionRequest.to_proto method."""

    def test_to_proto_basic(self) -> None:
        """Test to_proto with basic fields."""
        request = AmendPositionRequest(
            position_id=54321,
            stop_loss=1.11000,
            take_profit=1.15000,
        )

        proto = request.to_proto(account_id=11111)

        assert proto.ctid_trader_account_id == 11111
        assert proto.position_id == 54321
        assert proto.stop_loss == 1.11000
        assert proto.take_profit == 1.15000

    def test_to_proto_remove_sl_tp(self) -> None:
        """Test to_proto with None values removes SL/TP."""
        request = AmendPositionRequest(
            position_id=54321,
        )

        proto = request.to_proto(account_id=11111)

        # 0.0 means remove
        assert proto.stop_loss == 0.0
        assert proto.take_profit == 0.0

    def test_to_proto_with_trailing_stop(self) -> None:
        """Test to_proto with trailing stop."""
        request = AmendPositionRequest(
            position_id=54321,
            stop_loss=1.11000,
            trailing_stop_loss=True,
        )

        proto = request.to_proto(account_id=11111)

        assert proto.trailing_stop_loss is True

    def test_to_proto_with_trigger_method(self) -> None:
        """Test to_proto with stop loss trigger method."""
        request = AmendPositionRequest(
            position_id=54321,
            stop_loss=1.11000,
            stop_loss_trigger_method=StopTriggerMethod.OPPOSITE,
        )

        proto = request.to_proto(account_id=11111)

        assert proto.stop_loss_trigger_method.value == 2  # OPPOSITE


class TestClosePositionRequestToProto:
    """Tests for ClosePositionRequest.to_proto method."""

    def test_to_proto_full_close(self) -> None:
        """Test to_proto for full position close."""
        request = ClosePositionRequest(
            position_id=54321,
            volume=100000,
        )

        proto = request.to_proto(account_id=11111)

        assert proto.ctid_trader_account_id == 11111
        assert proto.position_id == 54321
        assert proto.volume == 100000

    def test_to_proto_partial_close(self) -> None:
        """Test to_proto for partial position close."""
        request = ClosePositionRequest(
            position_id=54321,
            volume=50000,  # Half the position
        )

        proto = request.to_proto(account_id=11111)

        assert proto.position_id == 54321
        assert proto.volume == 50000
