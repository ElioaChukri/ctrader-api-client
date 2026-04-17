"""Tests for deal models."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from ctrader_api_client.enums import DealStatus, OrderSide
from ctrader_api_client.models.deal import CloseDetail, Deal


class TestCloseDetail:
    """Tests for CloseDetail model."""

    def test_from_proto_maps_all_fields(self) -> None:
        """Test that from_proto correctly maps all proto fields."""
        proto = MagicMock()
        proto.entry_price = 1.12345
        proto.closed_volume = 100000
        proto.gross_profit = 50000  # 500.00 with 2 digits
        proto.swap = -1000  # -10.00
        proto.commission = -700  # -7.00
        proto.balance = 10500000  # 105000.00
        proto.money_digits = 2
        proto.pnl_conversion_fee = 50  # 0.50
        proto.quote_to_deposit_conversion_rate = 1.0
        proto.balance_version = 42

        detail = CloseDetail.from_proto(proto)

        assert detail.entry_price == 1.12345
        assert detail.closed_volume == 100000
        assert detail.gross_profit == 500.0  # Divided by 10^2
        assert detail.swap == -10.0
        assert detail.commission == -7.0
        assert detail.balance == 105000.0
        assert detail.pnl_conversion_fee == 0.5
        assert detail.quote_to_deposit_rate == 1.0
        assert detail.balance_version == 42


class TestDealFromProto:
    """Tests for Deal.from_proto method."""

    def test_from_proto_maps_all_fields(self) -> None:
        """Test that from_proto correctly maps all proto fields."""
        proto = MagicMock()
        proto.deal_id = 12345
        proto.order_id = 54321
        proto.position_id = 11111
        proto.symbol_id = 1
        proto.trade_side = 1  # BUY
        proto.volume = 100000
        proto.filled_volume = 100000
        proto.execution_price = 1.12345
        proto.execution_timestamp = 1704067200000
        proto.deal_status = 2  # FILLED
        proto.commission = -700  # -7.00 with 2 digits
        proto.money_digits = 2
        proto.create_timestamp = 1704067100000
        proto.utc_last_update_timestamp = 1704067200000
        proto.margin_rate = 0.01
        proto.base_to_usd_conversion_rate = 1.1
        proto.close_position_detail = None

        deal = Deal.from_proto(proto)

        assert deal.deal_id == 12345
        assert deal.order_id == 54321
        assert deal.position_id == 11111
        assert deal.symbol_id == 1
        assert deal.side == OrderSide.BUY
        assert deal.volume == 100000
        assert deal.filled_volume == 100000
        assert deal.execution_price == 1.12345
        assert deal.execution_timestamp == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        assert deal.status == DealStatus.FILLED
        assert deal.commission == -7.0  # Divided by 10^2
        assert deal.create_timestamp == datetime(2023, 12, 31, 23, 58, 20, tzinfo=UTC)
        assert deal.margin_rate == 0.01
        assert deal.base_to_usd_rate == 1.1
        assert deal.close_detail is None

    def test_from_proto_with_close_detail(self) -> None:
        """Test that from_proto correctly maps close detail."""
        close_detail = MagicMock()
        close_detail.entry_price = 1.11000
        close_detail.closed_volume = 100000
        close_detail.gross_profit = 50000  # 500.00
        close_detail.swap = -1000  # -10.00
        close_detail.commission = -700  # -7.00
        close_detail.balance = 10500000  # Must be > 0 to be considered a closing deal
        close_detail.money_digits = 2
        close_detail.pnl_conversion_fee = 0
        close_detail.quote_to_deposit_conversion_rate = 0
        close_detail.balance_version = 0

        proto = MagicMock()
        proto.deal_id = 12345
        proto.order_id = 54321
        proto.position_id = 11111
        proto.symbol_id = 1
        proto.trade_side = 2  # SELL (closing a buy)
        proto.volume = 100000
        proto.filled_volume = 100000
        proto.execution_price = 1.12345
        proto.execution_timestamp = 1704067200000
        proto.deal_status = 2
        proto.commission = -700
        proto.money_digits = 2
        proto.create_timestamp = 0
        proto.utc_last_update_timestamp = 0
        proto.margin_rate = 0
        proto.base_to_usd_conversion_rate = 0
        proto.close_position_detail = close_detail

        deal = Deal.from_proto(proto)

        assert deal.close_detail is not None
        assert deal.close_detail.entry_price == 1.11000
        assert deal.close_detail.closed_volume == 100000
        assert deal.close_detail.gross_profit == 500.0  # Divided by 10^2

    def test_from_proto_close_detail_requires_positive_balance(self) -> None:
        """Test that close_detail is None when balance is 0."""
        close_detail = MagicMock()
        close_detail.entry_price = 1.11000
        close_detail.closed_volume = 100000
        close_detail.gross_profit = 50000
        close_detail.swap = 0
        close_detail.commission = 0
        close_detail.balance = 0  # Zero balance = not a closing deal
        close_detail.money_digits = 2
        close_detail.pnl_conversion_fee = 0
        close_detail.quote_to_deposit_conversion_rate = 0
        close_detail.balance_version = 0

        proto = MagicMock()
        proto.deal_id = 12345
        proto.order_id = 54321
        proto.position_id = 11111
        proto.symbol_id = 1
        proto.trade_side = 1
        proto.volume = 100000
        proto.filled_volume = 100000
        proto.execution_price = 1.12345
        proto.execution_timestamp = 1704067200000
        proto.deal_status = 2
        proto.commission = 0
        proto.money_digits = 2
        proto.create_timestamp = 0
        proto.utc_last_update_timestamp = 0
        proto.margin_rate = 0
        proto.base_to_usd_conversion_rate = 0
        proto.close_position_detail = close_detail

        deal = Deal.from_proto(proto)

        assert deal.close_detail is None

    def test_from_proto_maps_deal_statuses(self) -> None:
        """Test that all deal statuses are correctly mapped."""
        proto = MagicMock()
        proto.deal_id = 1
        proto.order_id = 1
        proto.position_id = 1
        proto.symbol_id = 1
        proto.trade_side = 1
        proto.volume = 100000
        proto.filled_volume = 100000
        proto.execution_price = 1.12345
        proto.execution_timestamp = 1704067200000
        proto.commission = 0
        proto.money_digits = 2
        proto.create_timestamp = 0
        proto.utc_last_update_timestamp = 0
        proto.margin_rate = 0
        proto.base_to_usd_conversion_rate = 0
        proto.close_position_detail = None

        test_cases = [
            (2, DealStatus.FILLED),
            (3, DealStatus.PARTIALLY_FILLED),
            (4, DealStatus.REJECTED),
            (5, DealStatus.INTERNALLY_REJECTED),
            (6, DealStatus.ERROR),
            (7, DealStatus.MISSED),
        ]

        for proto_value, expected_status in test_cases:
            proto.deal_status = proto_value
            deal = Deal.from_proto(proto)
            assert deal.status == expected_status


class TestDealProperties:
    """Tests for Deal computed properties."""

    def test_is_closing_deal_true_with_close_detail(self) -> None:
        """Test is_closing_deal returns True when close_detail is present."""
        close_detail = CloseDetail(
            entry_price=1.11000,
            closed_volume=100000,
            gross_profit=500.0,
            swap=-10.0,
            commission=-7.0,
            balance=105000.0,
        )

        deal = Deal(
            deal_id=1,
            order_id=1,
            position_id=1,
            symbol_id=1,
            side=OrderSide.SELL,
            volume=100000,
            filled_volume=100000,
            execution_price=1.12345,
            execution_timestamp=datetime.now(UTC),
            status=DealStatus.FILLED,
            commission=-7.0,
            close_detail=close_detail,
        )

        assert deal.is_closing_deal is True

    def test_is_closing_deal_false_without_close_detail(self) -> None:
        """Test is_closing_deal returns False when close_detail is None."""
        deal = Deal(
            deal_id=1,
            order_id=1,
            position_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            filled_volume=100000,
            execution_price=1.12345,
            execution_timestamp=datetime.now(UTC),
            status=DealStatus.FILLED,
            commission=-7.0,
        )

        assert deal.is_closing_deal is False
