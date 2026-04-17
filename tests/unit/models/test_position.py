"""Tests for position model."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from ctrader_api_client.enums import OrderSide, PositionStatus, StopTriggerMethod
from ctrader_api_client.models import Position


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
        proto.swap = -500  # -5.00 with 2 digits
        proto.commission = -700  # -7.00 with 2 digits
        proto.used_margin = 1000000  # 10000.00 with 2 digits
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
        assert position.stop_loss == 1.11000
        assert position.take_profit == 1.15000
        assert position.trailing_stop_loss is True
        assert position.guaranteed_stop_loss is False
        assert position.stop_loss_trigger_method == StopTriggerMethod.TRADE
        assert position.swap == -5.0  # Divided by 10^2
        assert position.commission == -7.0  # Divided by 10^2
        assert position.used_margin == 10000.0  # Divided by 10^2
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
