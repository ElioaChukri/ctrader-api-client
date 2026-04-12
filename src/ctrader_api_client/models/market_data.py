from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from .._internal.proto import ProtoOATrendbarPeriod
from ..enums import TrendbarPeriod
from ._base import FrozenModel


if TYPE_CHECKING:
    from .._internal.proto import ProtoOATickData, ProtoOATrendbar
    from .symbol import Symbol


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
        low: Low price (raw integer).
        open: Open price (raw integer).
        high: High price (raw integer).
        close: Close price (raw integer).
        volume: Trade volume.
    """

    timestamp: datetime
    period: TrendbarPeriod
    low: int
    open: int
    high: int
    close: int
    volume: int

    def get_ohlc(self, symbol: Symbol) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """Get OHLC prices as Decimals.

        Args:
            symbol: Symbol for price conversion.

        Returns:
            Tuple of (open, high, low, close) as Decimals.
        """
        return (
            symbol.price_to_decimal(self.open),
            symbol.price_to_decimal(self.high),
            symbol.price_to_decimal(self.low),
            symbol.price_to_decimal(self.close),
        )

    def get_open(self, symbol: Symbol) -> Decimal:
        """Get open price as Decimal.

        Args:
            symbol: Symbol for price conversion.

        Returns:
            Open price.
        """
        return symbol.price_to_decimal(self.open)

    def get_high(self, symbol: Symbol) -> Decimal:
        """Get high price as Decimal.

        Args:
            symbol: Symbol for price conversion.

        Returns:
            High price.
        """
        return symbol.price_to_decimal(self.high)

    def get_low(self, symbol: Symbol) -> Decimal:
        """Get low price as Decimal.

        Args:
            symbol: Symbol for price conversion.

        Returns:
            Low price.
        """
        return symbol.price_to_decimal(self.low)

    def get_close(self, symbol: Symbol) -> Decimal:
        """Get close price as Decimal.

        Args:
            symbol: Symbol for price conversion.

        Returns:
            Close price.
        """
        return symbol.price_to_decimal(self.close)

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
            low=low,
            open=open_price,
            high=high,
            close=close,
            volume=proto.volume,
        )


class TickData(FrozenModel):
    """Historical tick data point.

    Represents a single price tick from tick history.

    Attributes:
        timestamp: Tick time.
        price: Tick price (raw integer).
    """

    timestamp: datetime
    price: int

    def get_price(self, symbol: Symbol) -> Decimal:
        """Get price as Decimal.

        Args:
            symbol: Symbol for price conversion.

        Returns:
            Price as Decimal.
        """
        return symbol.price_to_decimal(self.price)

    @classmethod
    def from_proto(cls, proto: ProtoOATickData, base_timestamp_ms: int = 0) -> TickData:
        """Create TickData from proto message.

        Args:
            proto: The proto message.
            base_timestamp_ms: Base timestamp in milliseconds. Proto timestamp
                is a delta from this base.

        Returns:
            A new TickData instance.
        """
        # Proto timestamp is delta from base in milliseconds
        actual_ts = base_timestamp_ms + proto.timestamp
        return cls(
            timestamp=datetime.fromtimestamp(actual_ts / 1000, tz=UTC),
            price=proto.tick,
        )
