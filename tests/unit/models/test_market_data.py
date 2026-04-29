"""Tests for market data models."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from ctrader_api_client.enums import TrendbarPeriod
from ctrader_api_client.models import TickData, Trendbar


class TestTrendbarFromProto:
    """Tests for Trendbar.from_proto method."""

    def test_from_proto_computes_ohlc_from_deltas(self) -> None:
        """Test that from_proto correctly computes OHLC from deltas."""
        proto = MagicMock()
        proto.utc_timestamp_in_minutes = 28401120  # 2024-01-01 00:00:00 UTC in minutes
        proto.period = 1  # M1
        proto.low = 112300  # 1.12300 raw
        proto.delta_open = 20  # open = low + 20 = 112320
        proto.delta_high = 50  # high = low + 50 = 112350
        proto.delta_close = 35  # close = low + 35 = 112335
        proto.volume = 1000

        bar = Trendbar.from_proto(proto)

        # Values are now floats, divided by 1e5
        assert bar.low == 1.123
        assert bar.open == 1.1232
        assert bar.high == 1.1235
        assert bar.close == 1.12335
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
            bar = Trendbar.from_proto(proto, bid_price=10)
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

        bar = Trendbar.from_proto(proto, bid_price=10)

        assert bar.timestamp == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)


class TestTrendbarValues:
    """Tests for Trendbar direct value access."""

    def test_ohlc_values_as_floats(self) -> None:
        """Test OHLC values are directly accessible as floats."""
        bar = Trendbar(
            timestamp=datetime.now(UTC),
            period=TrendbarPeriod.M1,
            low=1.12300,
            open=1.12320,
            high=1.12350,
            close=1.12335,
            volume=1000,
        )

        assert bar.open == 1.12320
        assert bar.high == 1.12350
        assert bar.low == 1.12300
        assert bar.close == 1.12335


class TestTickDataFromProto:
    """Tests for TickData.from_proto method."""

    def test_from_proto_converts_price(self) -> None:
        """Test that from_proto correctly converts price."""
        proto = MagicMock()
        proto.timestamp = 1704067200000  # 2024-01-01 00:00:00 UTC in ms
        proto.tick = 112345  # 1.12345 raw

        tick = TickData.from_proto(proto)

        assert tick.price == 1.12345
        expected_ts = datetime.fromtimestamp(1704067200.0, tz=UTC)
        assert tick.timestamp == expected_ts


class TestTickDataFromProtoList:
    """Tests for TickData.from_proto_list method."""

    def test_from_proto_list_handles_delta_encoding(self) -> None:
        """Test that from_proto_list correctly handles delta encoding."""
        # Create mock protos with delta-encoded timestamps and prices
        proto1 = MagicMock()
        proto1.timestamp = 1704067200000  # First is absolute
        proto1.tick = 112345  # First is absolute

        proto2 = MagicMock()
        proto2.timestamp = 1000  # +1 second delta
        proto2.tick = 10  # +10 price delta

        proto3 = MagicMock()
        proto3.timestamp = 500  # +0.5 second delta
        proto3.tick = -5  # -5 price delta

        ticks = TickData.from_proto_list([proto1, proto2, proto3])

        assert len(ticks) == 3

        # First tick: absolute values
        assert ticks[0].price == 1.12345
        assert ticks[0].timestamp == datetime.fromtimestamp(1704067200.0, tz=UTC)

        # Second tick: first + delta
        assert ticks[1].price == 1.12355  # 112345 + 10 = 112355 / 1e5
        assert ticks[1].timestamp == datetime.fromtimestamp(1704067201.0, tz=UTC)

        # Third tick: second + delta
        assert ticks[2].price == 1.1235  # 112355 - 5 = 112350 / 1e5
        assert ticks[2].timestamp == datetime.fromtimestamp(1704067201.5, tz=UTC)

    def test_from_proto_list_empty(self) -> None:
        """Test that from_proto_list handles empty list."""
        ticks = TickData.from_proto_list([])
        assert ticks == []
