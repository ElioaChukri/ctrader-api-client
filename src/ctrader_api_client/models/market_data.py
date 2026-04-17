from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .._internal.proto import ProtoOATrendbarPeriod
from ..enums import TrendbarPeriod
from ._base import FrozenModel


if TYPE_CHECKING:
    from .._internal.proto import ProtoOATickData, ProtoOATrendbar


_PERIOD_MAP: dict[int, TrendbarPeriod] = {
    ProtoOATrendbarPeriod.M1: TrendbarPeriod.M1,
    ProtoOATrendbarPeriod.M2: TrendbarPeriod.M2,
    ProtoOATrendbarPeriod.M3: TrendbarPeriod.M3,
    ProtoOATrendbarPeriod.M4: TrendbarPeriod.M4,
    ProtoOATrendbarPeriod.M5: TrendbarPeriod.M5,
    ProtoOATrendbarPeriod.M10: TrendbarPeriod.M10,
    ProtoOATrendbarPeriod.M15: TrendbarPeriod.M15,
    ProtoOATrendbarPeriod.M30: TrendbarPeriod.M30,
    ProtoOATrendbarPeriod.H1: TrendbarPeriod.H1,
    ProtoOATrendbarPeriod.H4: TrendbarPeriod.H4,
    ProtoOATrendbarPeriod.H12: TrendbarPeriod.H12,
    ProtoOATrendbarPeriod.D1: TrendbarPeriod.D1,
    ProtoOATrendbarPeriod.W1: TrendbarPeriod.W1,
    ProtoOATrendbarPeriod.MN1: TrendbarPeriod.MN1,
}


class Trendbar(FrozenModel):
    """Historical OHLC bar (candlestick).

    Note: The raw proto stores prices as deltas from low. This model
    exposes computed open/high/close values.

    Attributes:
        timestamp: Bar open time.
        period: Bar period (M1, H1, D1, etc.).
        low: Low price
        open: Open price
        high: High price
        close: Close price
        volume: Bar volume in ticks.
    """

    timestamp: datetime
    period: TrendbarPeriod
    open: float
    high: float
    low: float
    close: float
    volume: int

    @classmethod
    def from_proto(cls, proto: ProtoOATrendbar) -> Trendbar:
        """Create Trendbar from proto message.

        Args:
            proto: The proto message.

        Returns:
            A new Trendbar instance.
        """
        # Calculate timestamp from utc_timestamp_in_minutes
        ts = datetime.now(UTC)
        if proto.utc_timestamp_in_minutes:
            ts = datetime.fromtimestamp(proto.utc_timestamp_in_minutes * 60, tz=UTC)

        # Proto stores: low as absolute, others as deltas from low
        low = proto.low
        open_price = low + proto.delta_open
        high = low + proto.delta_high
        close = low + proto.delta_close

        return cls(
            timestamp=ts,
            period=_PERIOD_MAP.get(proto.period, TrendbarPeriod.M1),
            low=low / 1e5,
            open=open_price / 1e5,
            high=high / 1e5,
            close=close / 1e5,
            volume=proto.volume,
        )


class TickData(FrozenModel):
    """Historical tick data point.

    Represents a single price tick from tick history.

    Attributes:
        timestamp: Tick time.
        price: Tick price.
    """

    timestamp: datetime
    price: float

    @classmethod
    def from_proto(cls, proto: ProtoOATickData) -> TickData:
        """Create TickData from proto message.

        Note that price needs to be converted from a raw integer to a float by dividing by 1e5.

        Args:
            proto: The proto message.

        Returns:
            A new TickData instance.
        """
        # Proto timestamp is delta from base in milliseconds
        return cls(
            timestamp=datetime.fromtimestamp(proto.timestamp / 1000, tz=UTC),
            price=proto.tick / 1e5,
        )

    @classmethod
    def from_proto_list(cls, protos: list[ProtoOATickData]) -> Sequence[TickData]:
        """Convert list of proto tick data to list of TickData.

        Note that proto timestamps and prices are stored as deltas from the previous timestamp and price, with
        the first data point being an absolute value.
        This method converts them to absolute values.

        Additionally, price needs to be converted from a raw integer to a float by dividing by 1e5.

        Args:
            protos: List of proto tick data messages.

        Returns:
            List of TickData instances.
        """
        if not protos:
            return []

        ticks = []
        current_timestamp = 0
        current_price = 0

        for proto in protos:
            current_timestamp += proto.timestamp
            current_price += proto.tick

            ticks.append(
                cls(
                    timestamp=datetime.fromtimestamp(current_timestamp / 1000, tz=UTC),
                    price=current_price / 1e5,
                )
            )

        return ticks
