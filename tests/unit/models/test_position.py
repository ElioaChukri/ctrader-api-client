"""Tests for position model."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

from ctrader_api_client.enums import OrderSide, PositionStatus, StopTriggerMethod, TradingMode
from ctrader_api_client.models import Position, Symbol


def _create_symbol(digits: int = 5) -> Symbol:
    """Create a Symbol for testing."""
    return Symbol(
        symbol_id=1,
        digits=digits,
        pip_position=4,
        lot_size=100000,
        min_volume=1000,
        max_volume=10000000,
        step_volume=1000,
        trading_mode=TradingMode.ENABLED,
        swap_long=0.0,
        swap_short=0.0,
    )


class TestPositionFromProto:
    """Tests for Position.from_proto method."""

    def test_from_proto_maps_all_fields(self) -> None:
        """Test that from_proto correctly maps all proto fields."""
        trade_data = MagicMock()
        trade_data.symbol_id = 1
        trade_data.volume = 100000
        trade_data.trade_side = 1  # BUY
        trade_data.open_timestamp = 1704067200000  # 2024-01-01 00:00:00 UTC
        trade_data.label = "test_label"
        trade_data.comment = "test_comment"
        trade_data.guaranteed_stop_loss = False
        trade_data.close_timestamp = 0

        proto = MagicMock()
        proto.position_id = 12345
        proto.trade_data = trade_data
        proto.position_status = 1  # OPEN
        proto.price = 1.12345
        proto.stop_loss = 1.11000
        proto.take_profit = 1.15000
        proto.swap = -500
        proto.commission = -700
        proto.used_margin = 1000000
        proto.margin_rate = 0.01
        proto.money_digits = 2
        proto.trailing_stop_loss = True
        proto.guaranteed_stop_loss = False
        proto.stop_loss_trigger_method = 1  # TRADE
        proto.utc_last_update_timestamp = 1704153600000  # 2024-01-02 00:00:00 UTC

        position = Position.from_proto(proto)

        assert position.position_id == 12345
        assert position.symbol_id == 1
        assert position.side == OrderSide.BUY
        assert position.volume == 100000
        assert position.entry_price == 1.12345
        assert position.status == PositionStatus.OPEN
        assert position.open_timestamp == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        assert position.money_digits == 2
        assert position.stop_loss == 1.11000
        assert position.take_profit == 1.15000
        assert position.trailing_stop_loss is True
        assert position.guaranteed_stop_loss is False
        assert position.stop_loss_trigger_method == StopTriggerMethod.TRADE
        assert position.swap == -500
        assert position.commission == -700
        assert position.used_margin == 1000000
        assert position.margin_rate == 0.01
        assert position.label == "test_label"
        assert position.comment == "test_comment"
        assert position.last_update_timestamp == datetime(2024, 1, 2, 0, 0, 0, tzinfo=UTC)

    def test_from_proto_maps_sell_side(self) -> None:
        """Test that from_proto correctly maps SELL side."""
        trade_data = MagicMock()
        trade_data.symbol_id = 1
        trade_data.volume = 100000
        trade_data.trade_side = 2  # SELL
        trade_data.open_timestamp = 1704067200000
        trade_data.label = ""
        trade_data.comment = ""
        trade_data.close_timestamp = 0

        proto = MagicMock()
        proto.position_id = 1
        proto.trade_data = trade_data
        proto.position_status = 1
        proto.price = 1.12345
        proto.stop_loss = 0
        proto.take_profit = 0
        proto.swap = 0
        proto.commission = 0
        proto.used_margin = 0
        proto.margin_rate = 0
        proto.money_digits = 2
        proto.trailing_stop_loss = False
        proto.guaranteed_stop_loss = False
        proto.stop_loss_trigger_method = 1
        proto.utc_last_update_timestamp = 0

        position = Position.from_proto(proto)

        assert position.side == OrderSide.SELL

    def test_from_proto_maps_position_statuses(self) -> None:
        """Test that all position statuses are correctly mapped."""
        trade_data = MagicMock()
        trade_data.symbol_id = 1
        trade_data.volume = 100000
        trade_data.trade_side = 1
        trade_data.open_timestamp = 1704067200000
        trade_data.label = ""
        trade_data.comment = ""
        trade_data.close_timestamp = 0

        proto = MagicMock()
        proto.position_id = 1
        proto.trade_data = trade_data
        proto.price = 1.12345
        proto.stop_loss = 0
        proto.take_profit = 0
        proto.swap = 0
        proto.commission = 0
        proto.used_margin = 0
        proto.margin_rate = 0
        proto.money_digits = 2
        proto.trailing_stop_loss = False
        proto.guaranteed_stop_loss = False
        proto.stop_loss_trigger_method = 1
        proto.utc_last_update_timestamp = 0

        test_cases = [
            (1, PositionStatus.OPEN),
            (2, PositionStatus.CLOSED),
            (3, PositionStatus.CREATED),
            (4, PositionStatus.ERROR),
        ]

        for proto_value, expected_status in test_cases:
            proto.position_status = proto_value
            position = Position.from_proto(proto)
            assert position.status == expected_status

    def test_from_proto_maps_trigger_methods(self) -> None:
        """Test that all trigger methods are correctly mapped."""
        trade_data = MagicMock()
        trade_data.symbol_id = 1
        trade_data.volume = 100000
        trade_data.trade_side = 1
        trade_data.open_timestamp = 1704067200000
        trade_data.label = ""
        trade_data.comment = ""
        trade_data.close_timestamp = 0

        proto = MagicMock()
        proto.position_id = 1
        proto.trade_data = trade_data
        proto.position_status = 1
        proto.price = 1.12345
        proto.stop_loss = 0
        proto.take_profit = 0
        proto.swap = 0
        proto.commission = 0
        proto.used_margin = 0
        proto.margin_rate = 0
        proto.money_digits = 2
        proto.trailing_stop_loss = False
        proto.guaranteed_stop_loss = False
        proto.utc_last_update_timestamp = 0

        test_cases = [
            (1, StopTriggerMethod.TRADE),
            (2, StopTriggerMethod.OPPOSITE),
            (3, StopTriggerMethod.DOUBLE_TRADE),
            (4, StopTriggerMethod.DOUBLE_OPPOSITE),
        ]

        for proto_value, expected_method in test_cases:
            proto.stop_loss_trigger_method = proto_value
            position = Position.from_proto(proto)
            assert position.stop_loss_trigger_method == expected_method


class TestPositionHelpers:
    """Tests for Position helper methods."""

    def test_get_entry_price(self) -> None:
        """Test get_entry_price returns correct Decimal."""
        position = Position(
            position_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            entry_price=1.12345,
            status=PositionStatus.OPEN,
            open_timestamp=datetime.now(UTC),
            money_digits=2,
        )
        symbol = _create_symbol(digits=5)

        result = position.get_entry_price(symbol)
        assert result == Decimal("1.12345")

    def test_get_stop_loss_when_set(self) -> None:
        """Test get_stop_loss returns correct Decimal when set."""
        position = Position(
            position_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            entry_price=1.12345,
            status=PositionStatus.OPEN,
            open_timestamp=datetime.now(UTC),
            money_digits=2,
            stop_loss=1.11000,
        )
        symbol = _create_symbol(digits=5)

        result = position.get_stop_loss(symbol)
        assert result == Decimal("1.11000")

    def test_get_stop_loss_when_none(self) -> None:
        """Test get_stop_loss returns None when not set."""
        position = Position(
            position_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            entry_price=1.12345,
            status=PositionStatus.OPEN,
            open_timestamp=datetime.now(UTC),
            money_digits=2,
        )
        symbol = _create_symbol()

        result = position.get_stop_loss(symbol)
        assert result is None

    def test_get_take_profit_when_set(self) -> None:
        """Test get_take_profit returns correct Decimal when set."""
        position = Position(
            position_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            entry_price=1.12345,
            status=PositionStatus.OPEN,
            open_timestamp=datetime.now(UTC),
            money_digits=2,
            take_profit=1.15000,
        )
        symbol = _create_symbol(digits=5)

        result = position.get_take_profit(symbol)
        assert result == Decimal("1.15000")

    def test_get_take_profit_when_none(self) -> None:
        """Test get_take_profit returns None when not set."""
        position = Position(
            position_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            entry_price=1.12345,
            status=PositionStatus.OPEN,
            open_timestamp=datetime.now(UTC),
            money_digits=2,
        )
        symbol = _create_symbol()

        result = position.get_take_profit(symbol)
        assert result is None

    def test_get_swap(self) -> None:
        """Test get_swap returns correct Decimal."""
        position = Position(
            position_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            entry_price=1.12345,
            status=PositionStatus.OPEN,
            open_timestamp=datetime.now(UTC),
            money_digits=2,
            swap=-1250,  # -12.50
        )

        result = position.get_swap()
        assert result == Decimal("-12.50")

    def test_get_commission(self) -> None:
        """Test get_commission returns correct Decimal."""
        position = Position(
            position_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            entry_price=1.12345,
            status=PositionStatus.OPEN,
            open_timestamp=datetime.now(UTC),
            money_digits=2,
            commission=-700,  # -7.00
        )

        result = position.get_commission()
        assert result == Decimal("-7.00")

    def test_get_volume_in_lots(self) -> None:
        """Test get_volume_in_lots returns correct value."""
        position = Position(
            position_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,  # 1000 lots as Decimal("1000")
            entry_price=1.12345,
            status=PositionStatus.OPEN,
            open_timestamp=datetime.now(UTC),
            money_digits=2,
        )
        symbol = _create_symbol()

        result = position.get_volume_in_lots(symbol)
        assert result == Decimal("1000")  # 100000 / 100 = 1000
