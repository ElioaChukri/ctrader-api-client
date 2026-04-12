"""Tests for market data models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

from ctrader_api_client.enums import TradingMode, TrendbarPeriod
from ctrader_api_client.models import Symbol, TickData, Trendbar


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


class TestTrendbarFromProto:
    """Tests for Trendbar.from_proto method."""

    def test_from_proto_computes_ohlc_from_deltas(self) -> None:
        """Test that from_proto correctly computes OHLC from deltas."""
        proto = MagicMock()
        proto.utc_timestamp_in_minutes = 28401120  # 2024-01-01 00:00:00 UTC in minutes
        proto.period = 1  # M1
        proto.low = 112300  # 1.12300
        proto.delta_open = 20  # open = low + 20 = 112320
        proto.delta_high = 50  # high = low + 50 = 112350
        proto.delta_close = 35  # close = low + 35 = 112335
        proto.volume = 1000

        bar = Trendbar.from_proto(proto)

        assert bar.low == 112300
        assert bar.open == 112320
        assert bar.high == 112350
        assert bar.close == 112335
        assert bar.volume == 1000
        assert bar.period == TrendbarPeriod.M1

    def test_from_proto_maps_all_periods(self) -> None:
        """Test that all periods are correctly mapped."""
        proto = MagicMock()
        proto.utc_timestamp_in_minutes = 28401120
        proto.low = 112300
        proto.delta_open = 0
        proto.delta_high = 0
        proto.delta_close = 0
        proto.volume = 1000

        test_cases = [
            (1, TrendbarPeriod.M1),
            (2, TrendbarPeriod.M2),
            (3, TrendbarPeriod.M3),
            (4, TrendbarPeriod.M4),
            (5, TrendbarPeriod.M5),
            (6, TrendbarPeriod.M10),
            (7, TrendbarPeriod.M15),
            (8, TrendbarPeriod.M30),
            (9, TrendbarPeriod.H1),
            (10, TrendbarPeriod.H4),
            (11, TrendbarPeriod.H12),
            (12, TrendbarPeriod.D1),
            (13, TrendbarPeriod.W1),
            (14, TrendbarPeriod.MN1),
        ]

        for proto_value, expected_period in test_cases:
            proto.period = proto_value
            bar = Trendbar.from_proto(proto)
            assert bar.period == expected_period

    def test_from_proto_converts_timestamp(self) -> None:
        """Test that timestamp is correctly converted from minutes."""
        proto = MagicMock()
        # 28401120 minutes = 1704067200 seconds = 2024-01-01 00:00:00 UTC
        proto.utc_timestamp_in_minutes = 28401120
        proto.period = 1
        proto.low = 112300
        proto.delta_open = 0
        proto.delta_high = 0
        proto.delta_close = 0
        proto.volume = 1000

        bar = Trendbar.from_proto(proto)

        assert bar.timestamp == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)


class TestTrendbarHelpers:
    """Tests for Trendbar helper methods."""

    def test_get_ohlc(self) -> None:
        """Test get_ohlc returns correct tuple of Decimals."""
        bar = Trendbar(
            timestamp=datetime.now(UTC),
            period=TrendbarPeriod.M1,
            low=112300,
            open=112320,
            high=112350,
            close=112335,
            volume=1000,
        )
        symbol = _create_symbol(digits=5)

        o, h, l, c = bar.get_ohlc(symbol)

        assert o == Decimal("1.12320")
        assert h == Decimal("1.12350")
        assert l == Decimal("1.12300")
        assert c == Decimal("1.12335")

    def test_get_open(self) -> None:
        """Test get_open returns correct Decimal."""
        bar = Trendbar(
            timestamp=datetime.now(UTC),
            period=TrendbarPeriod.M1,
            low=112300,
            open=112320,
            high=112350,
            close=112335,
            volume=1000,
        )
        symbol = _create_symbol(digits=5)

        result = bar.get_open(symbol)
        assert result == Decimal("1.12320")

    def test_get_high(self) -> None:
        """Test get_high returns correct Decimal."""
        bar = Trendbar(
            timestamp=datetime.now(UTC),
            period=TrendbarPeriod.M1,
            low=112300,
            open=112320,
            high=112350,
            close=112335,
            volume=1000,
        )
        symbol = _create_symbol(digits=5)

        result = bar.get_high(symbol)
        assert result == Decimal("1.12350")

    def test_get_low(self) -> None:
        """Test get_low returns correct Decimal."""
        bar = Trendbar(
            timestamp=datetime.now(UTC),
            period=TrendbarPeriod.M1,
            low=112300,
            open=112320,
            high=112350,
            close=112335,
            volume=1000,
        )
        symbol = _create_symbol(digits=5)

        result = bar.get_low(symbol)
        assert result == Decimal("1.12300")

    def test_get_close(self) -> None:
        """Test get_close returns correct Decimal."""
        bar = Trendbar(
            timestamp=datetime.now(UTC),
            period=TrendbarPeriod.M1,
            low=112300,
            open=112320,
            high=112350,
            close=112335,
            volume=1000,
        )
        symbol = _create_symbol(digits=5)

        result = bar.get_close(symbol)
        assert result == Decimal("1.12335")

    def test_ohlc_with_jpy_pair(self) -> None:
        """Test OHLC conversion for JPY pairs (3 digits)."""
        bar = Trendbar(
            timestamp=datetime.now(UTC),
            period=TrendbarPeriod.H1,
            low=150123,  # 150.123
            open=150145,
            high=150200,
            close=150180,
            volume=5000,
        )
        symbol = _create_symbol(digits=3)

        o, h, low, c = bar.get_ohlc(symbol)

        assert o == Decimal("150.145")
        assert h == Decimal("150.200")
        assert low == Decimal("150.123")
        assert c == Decimal("150.180")


class TestTickDataFromProto:
    """Tests for TickData.from_proto method."""

    def test_from_proto_with_base_timestamp(self) -> None:
        """Test that from_proto correctly computes timestamp from base."""
        proto = MagicMock()
        proto.timestamp = 500  # 500ms delta
        proto.tick = 112345

        # Base: 2024-01-01 00:00:00 UTC in ms
        base_ts = 1704067200000

        tick = TickData.from_proto(proto, base_timestamp_ms=base_ts)

        assert tick.price == 112345
        # 1704067200000 + 500 = 1704067200500
        expected_ts = datetime.fromtimestamp(1704067200.500, tz=UTC)
        assert tick.timestamp == expected_ts

    def test_from_proto_zero_delta(self) -> None:
        """Test that from_proto handles zero delta."""
        proto = MagicMock()
        proto.timestamp = 0
        proto.tick = 112345

        base_ts = 1704067200000

        tick = TickData.from_proto(proto, base_timestamp_ms=base_ts)

        expected_ts = datetime.fromtimestamp(1704067200.0, tz=UTC)
        assert tick.timestamp == expected_ts


class TestTickDataHelpers:
    """Tests for TickData helper methods."""

    def test_get_price(self) -> None:
        """Test get_price returns correct Decimal."""
        tick = TickData(
            timestamp=datetime.now(UTC),
            price=112345,  # 1.12345
        )
        symbol = _create_symbol(digits=5)

        result = tick.get_price(symbol)
        assert result == Decimal("1.12345")

    def test_get_price_jpy_pair(self) -> None:
        """Test get_price for JPY pairs."""
        tick = TickData(
            timestamp=datetime.now(UTC),
            price=150123,  # 150.123
        )
        symbol = _create_symbol(digits=3)

        result = tick.get_price(symbol)
        assert result == Decimal("150.123")
