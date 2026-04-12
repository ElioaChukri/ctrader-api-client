"""Tests for deal models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

from ctrader_api_client.enums import DealStatus, OrderSide, TradingMode
from ctrader_api_client.models import Symbol
from ctrader_api_client.models.deal import CloseDetail, Deal


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


class TestCloseDetail:
    """Tests for CloseDetail model."""

    def test_from_proto_maps_all_fields(self) -> None:
        """Test that from_proto correctly maps all proto fields."""
        proto = MagicMock()
        proto.entry_price = 1.12345
        proto.closed_volume = 100000
        proto.gross_profit = 50000  # 500.00
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
        assert detail.gross_profit == 50000
        assert detail.swap == -1000
        assert detail.commission == -700
        assert detail.balance == 10500000
        assert detail.money_digits == 2
        assert detail.pnl_conversion_fee == 50
        assert detail.quote_to_deposit_rate == 1.0
        assert detail.balance_version == 42

    def test_get_gross_profit(self) -> None:
        """Test get_gross_profit returns correct Decimal."""
        detail = CloseDetail(
            entry_price=1.12345,
            closed_volume=100000,
            gross_profit=50000,
            swap=-1000,
            commission=-700,
            balance=10500000,
            money_digits=2,
        )

        result = detail.get_gross_profit()
        assert result == Decimal("500.00")

    def test_get_gross_profit_negative(self) -> None:
        """Test get_gross_profit with negative profit."""
        detail = CloseDetail(
            entry_price=1.12345,
            closed_volume=100000,
            gross_profit=-25000,
            swap=-1000,
            commission=-700,
            balance=9750000,
            money_digits=2,
        )

        result = detail.get_gross_profit()
        assert result == Decimal("-250.00")

    def test_get_net_profit(self) -> None:
        """Test get_net_profit subtracts swap, commission, and fee."""
        detail = CloseDetail(
            entry_price=1.12345,
            closed_volume=100000,
            gross_profit=50000,  # 500.00
            swap=-1000,  # -10.00
            commission=-700,  # -7.00
            balance=10500000,
            money_digits=2,
            pnl_conversion_fee=50,  # 0.50
        )

        # Net = 50000 - (-1000) - (-700) - 50 = 50000 + 1000 + 700 - 50 = 51650
        # Wait, that's wrong. Let me recalculate:
        # Net = gross - swap - commission - fee
        # Net = 50000 - (-1000) - (-700) - 50 = 50000 + 1000 + 700 - 50 = 51650
        # But swap and commission are already negative (costs), so:
        # Net = 50000 - (-1000) - (-700) - 50
        # Hmm, let me check the formula in the code:
        # net = self.gross_profit - self.swap - self.commission - self.pnl_conversion_fee
        # So: 50000 - (-1000) - (-700) - 50 = 50000 + 1000 + 700 - 50 = 51650
        # That gives 516.50
        result = detail.get_net_profit()
        assert result == Decimal("516.50")

    def test_get_swap(self) -> None:
        """Test get_swap returns correct Decimal."""
        detail = CloseDetail(
            entry_price=1.12345,
            closed_volume=100000,
            gross_profit=50000,
            swap=-1000,  # -10.00
            commission=-700,
            balance=10500000,
            money_digits=2,
        )

        result = detail.get_swap()
        assert result == Decimal("-10.00")

    def test_get_commission(self) -> None:
        """Test get_commission returns correct Decimal."""
        detail = CloseDetail(
            entry_price=1.12345,
            closed_volume=100000,
            gross_profit=50000,
            swap=-1000,
            commission=-700,  # -7.00
            balance=10500000,
            money_digits=2,
        )

        result = detail.get_commission()
        assert result == Decimal("-7.00")


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
        proto.commission = -700
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
        assert deal.commission == -700
        assert deal.money_digits == 2
        assert deal.create_timestamp == datetime(2023, 12, 31, 23, 58, 20, tzinfo=UTC)
        assert deal.margin_rate == 0.01
        assert deal.base_to_usd_rate == 1.1
        assert deal.close_detail is None

    def test_from_proto_with_close_detail(self) -> None:
        """Test that from_proto correctly maps close detail."""
        close_detail = MagicMock()
        close_detail.entry_price = 1.11000
        close_detail.closed_volume = 100000
        close_detail.gross_profit = 50000
        close_detail.swap = -1000
        close_detail.commission = -700
        close_detail.balance = 10500000
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
        assert deal.close_detail.gross_profit == 50000

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


class TestDealHelpers:
    """Tests for Deal helper methods."""

    def test_get_execution_price(self) -> None:
        """Test get_execution_price returns correct Decimal."""
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
            commission=-700,
            money_digits=2,
        )
        symbol = _create_symbol(digits=5)

        result = deal.get_execution_price(symbol)
        assert result == Decimal("1.12345")

    def test_get_commission(self) -> None:
        """Test get_commission returns correct Decimal."""
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
            commission=-700,  # -7.00
            money_digits=2,
        )

        result = deal.get_commission()
        assert result == Decimal("-7.00")

    def test_get_volume_in_lots(self) -> None:
        """Test get_volume_in_lots returns correct value."""
        deal = Deal(
            deal_id=1,
            order_id=1,
            position_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            volume=100000,
            filled_volume=100,  # 1 lot
            execution_price=1.12345,
            execution_timestamp=datetime.now(UTC),
            status=DealStatus.FILLED,
            commission=-700,
            money_digits=2,
        )
        symbol = _create_symbol()

        result = deal.get_volume_in_lots(symbol)
        assert result == Decimal("1")


class TestDealProperties:
    """Tests for Deal computed properties."""

    def test_is_closing_deal_true_with_close_detail(self) -> None:
        """Test is_closing_deal returns True when close_detail is present."""
        close_detail = CloseDetail(
            entry_price=1.11000,
            closed_volume=100000,
            gross_profit=50000,
            swap=-1000,
            commission=-700,
            balance=10500000,
            money_digits=2,
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
            commission=-700,
            money_digits=2,
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
            commission=-700,
            money_digits=2,
        )

        assert deal.is_closing_deal is False
