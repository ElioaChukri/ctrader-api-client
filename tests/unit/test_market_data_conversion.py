"""Conversion rules for market data coming off the wire.

The API sends prices as scaled integers and encodes bars and ticks as deltas.
Getting any of this wrong produces plausible-looking but wrong prices, so the
arithmetic is pinned here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ctrader_api_client._internal.proto import ProtoOATickData, ProtoOATrendbar, ProtoOATrendbarPeriod
from ctrader_api_client.enums import TrendbarPeriod
from ctrader_api_client.models import TickData, Trendbar


def bar(
    *,
    low: int = 100_000,
    delta_open: int = 0,
    delta_high: int = 0,
    delta_close: int = 0,
    minutes: int = 29_000_000,
    period: ProtoOATrendbarPeriod = ProtoOATrendbarPeriod.M1,
    volume: int = 0,
) -> ProtoOATrendbar:
    return ProtoOATrendbar(
        low=low,
        delta_open=delta_open,
        delta_high=delta_high,
        delta_close=delta_close,
        utc_timestamp_in_minutes=minutes,
        period=period,
        volume=volume,
    )


def test_bar_prices_are_rebuilt_from_deltas_above_the_low() -> None:
    trendbar = Trendbar.from_proto(bar(low=110_000, delta_open=2_000, delta_high=5_000, delta_close=1_000))

    assert (trendbar.low, trendbar.open, trendbar.high, trendbar.close) == (
        Decimal("1.10000"),
        Decimal("1.12000"),
        Decimal("1.15000"),
        Decimal("1.11000"),
    )


def test_bar_timestamp_is_the_minute_count_in_utc() -> None:
    trendbar = Trendbar.from_proto(bar(minutes=29_000_000, delta_close=1))

    assert trendbar.timestamp == datetime.fromtimestamp(29_000_000 * 60, tz=UTC)


def test_bar_volume_is_carried_through() -> None:
    trendbar = Trendbar.from_proto(bar(delta_close=1, volume=4_242))

    assert trendbar.volume == 4_242


@pytest.mark.parametrize(
    ("proto_period", "expected"),
    [
        (ProtoOATrendbarPeriod.M1, TrendbarPeriod.M1),
        (ProtoOATrendbarPeriod.M15, TrendbarPeriod.M15),
        (ProtoOATrendbarPeriod.H4, TrendbarPeriod.H4),
        (ProtoOATrendbarPeriod.D1, TrendbarPeriod.D1),
        (ProtoOATrendbarPeriod.MN1, TrendbarPeriod.MN1),
    ],
)
def test_bar_period_is_translated(proto_period: ProtoOATrendbarPeriod, expected: TrendbarPeriod) -> None:
    trendbar = Trendbar.from_proto(bar(period=proto_period, delta_close=1))

    assert trendbar.period == expected


def test_a_live_bar_without_a_close_is_rejected() -> None:
    """Accepting it would report a close equal to the low, which reads as a real price."""
    with pytest.raises(RuntimeError):
        Trendbar.from_proto(bar(delta_close=0), historical=False)


def test_a_historical_bar_may_close_at_its_low() -> None:
    trendbar = Trendbar.from_proto(bar(low=110_000, delta_close=0), historical=True)

    assert trendbar.close == Decimal("1.10000")


def test_a_supplied_bid_price_becomes_the_close() -> None:
    """Live bars close at the current bid, which arrives in the same scaled units."""
    trendbar = Trendbar.from_proto(bar(low=110_000, delta_close=9_999), bid_price=Decimal(123_456))

    assert trendbar.close == Decimal("1.23456")


def test_a_supplied_bid_price_makes_a_missing_close_acceptable() -> None:
    trendbar = Trendbar.from_proto(bar(delta_close=0), bid_price=Decimal(150_000))

    assert trendbar.close == Decimal("1.50000")


def test_a_single_tick_is_scaled_from_its_integer_price() -> None:
    tick = TickData.from_proto(ProtoOATickData(timestamp=1_700_000_000_000, tick=123_456))

    assert tick.price == Decimal("1.23456")
    assert tick.timestamp == datetime.fromtimestamp(1_700_000_000, tz=UTC)


def test_a_tick_series_accumulates_its_deltas() -> None:
    """Only the first tick is absolute; the rest are relative to their predecessor."""
    ticks = TickData.from_proto_list(
        [
            ProtoOATickData(timestamp=1_700_000_000_000, tick=100_000),
            ProtoOATickData(timestamp=1_000, tick=500),
            ProtoOATickData(timestamp=2_000, tick=-1_500),
        ]
    )

    assert [tick.price for tick in ticks] == [Decimal("1.00000"), Decimal("1.00500"), Decimal("0.99000")]
    assert [tick.timestamp.timestamp() for tick in ticks] == [1_700_000_000, 1_700_000_001, 1_700_000_003]


def test_an_empty_tick_series_stays_empty() -> None:
    assert TickData.from_proto_list([]) == []
