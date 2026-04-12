from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from .._internal.proto import ProtoOATradingMode
from ..enums import TradingMode
from ._base import FrozenModel


if TYPE_CHECKING:
    from .._internal.proto import ProtoOALightSymbol, ProtoOASymbol


_TRADING_MODE_MAP: dict[int, TradingMode] = {
    ProtoOATradingMode.ENABLED: TradingMode.ENABLED,
    ProtoOATradingMode.DISABLED_WITHOUT_PENDINGS_EXECUTION: TradingMode.DISABLED_WITHOUT_PENDINGS_EXECUTION,
    ProtoOATradingMode.DISABLED_WITH_PENDINGS_EXECUTION: TradingMode.DISABLED_WITH_PENDINGS_EXECUTION,
    ProtoOATradingMode.CLOSE_ONLY_MODE: TradingMode.CLOSE_ONLY,
}


class SymbolInfo(FrozenModel):
    """Basic symbol information from symbol list.

    This is the lightweight representation returned when listing symbols.
    Use Symbol for full trading parameters.

    Attributes:
        symbol_id: The unique symbol identifier.
        name: Symbol name (e.g., "EURUSD").
        enabled: Whether the symbol is enabled for trading.
        base_asset_id: Asset ID of the base currency.
        quote_asset_id: Asset ID of the quote currency.
        category_id: Symbol category ID.
        description: Human-readable description.
    """

    symbol_id: int
    name: str
    enabled: bool
    base_asset_id: int
    quote_asset_id: int
    category_id: int | None = None
    description: str = ""

    @classmethod
    def from_proto(cls, proto: ProtoOALightSymbol) -> SymbolInfo:
        """Create SymbolInfo from proto message.

        Args:
            proto: The proto message to convert.

        Returns:
            A new SymbolInfo instance.
        """
        return cls(
            symbol_id=proto.symbol_id,
            name=proto.symbol_name,
            enabled=proto.enabled,
            base_asset_id=proto.base_asset_id,
            quote_asset_id=proto.quote_asset_id,
            category_id=proto.symbol_category_id if proto.symbol_category_id else None,
            description=proto.description or "",
        )


class Symbol(FrozenModel):
    """Full symbol trading parameters.

    Contains all information needed for trading calculations including
    pip position, lot size, volume limits, and swap rates.

    Attributes:
        symbol_id: The unique symbol identifier.
        digits: Price decimal places.
        pip_position: Position of pip in price (e.g., 4 means 0.0001).
        lot_size: Contract size in base units (e.g., 100000 for forex).
        min_volume: Minimum order volume in cents.
        max_volume: Maximum order volume in cents.
        step_volume: Volume step in cents.
        trading_mode: Current trading mode.
        swap_long: Swap rate for long positions.
        swap_short: Swap rate for short positions.
        commission: Commission rate.
        max_exposure: Maximum allowed exposure.
        leverage_id: ID of dynamic leverage profile, if any.
        enable_short_selling: Whether short selling is allowed.
        guaranteed_stop_loss: Whether guaranteed stop loss is available.
        sl_distance: Minimum stop loss distance.
        tp_distance: Minimum take profit distance.
        schedule_timezone: Timezone for trading schedule.
        measurement_units: Measurement units (e.g., "oz" for gold).
    """

    symbol_id: int
    digits: int
    pip_position: int
    lot_size: int
    min_volume: int
    max_volume: int
    step_volume: int
    trading_mode: TradingMode
    swap_long: float
    swap_short: float

    # Optional fields
    commission: int = 0
    max_exposure: int | None = None
    leverage_id: int | None = None
    enable_short_selling: bool = True
    guaranteed_stop_loss: bool = False
    sl_distance: int = 0
    tp_distance: int = 0
    schedule_timezone: str = ""
    measurement_units: str = ""

    def price_to_decimal(self, raw_price: int) -> Decimal:
        """Convert raw price integer to Decimal.

        Args:
            raw_price: Raw price from API.

        Returns:
            Price as Decimal with correct precision.
        """
        return Decimal(raw_price) / Decimal(10**self.digits)

    def decimal_to_price(self, price: Decimal) -> int:
        """Convert Decimal price to raw integer.

        Args:
            price: Price as Decimal.

        Returns:
            Raw price integer for API.
        """
        return int(price * Decimal(10**self.digits))

    @staticmethod
    def volume_to_lots(volume_cents: int) -> Decimal:
        """Convert volume in cents to lots.

        Args:
            volume_cents: Volume in cents (100 = 0.01 lots).

        Returns:
            Volume in lots.
        """
        return Decimal(volume_cents) / Decimal(100)

    @staticmethod
    def lots_to_volume(lots: Decimal) -> int:
        """Convert lots to volume in cents.

        Args:
            lots: Volume in lots.

        Returns:
            Volume in cents for API.
        """
        return int(lots * 100)

    @classmethod
    def from_proto(cls, proto: ProtoOASymbol) -> Symbol:
        """Create Symbol from proto message.

        Args:
            proto: The proto message to convert.

        Returns:
            A new Symbol instance.
        """
        return cls(
            symbol_id=proto.symbol_id,
            digits=proto.digits,
            pip_position=proto.pip_position,
            lot_size=proto.lot_size,
            min_volume=proto.min_volume,
            max_volume=proto.max_volume,
            step_volume=proto.step_volume,
            trading_mode=_TRADING_MODE_MAP.get(proto.trading_mode, TradingMode.ENABLED),
            swap_long=proto.swap_long,
            swap_short=proto.swap_short,
            commission=proto.commission if proto.commission else 0,
            max_exposure=proto.max_exposure if proto.max_exposure else None,
            leverage_id=proto.leverage_id if proto.leverage_id else None,
            enable_short_selling=proto.enable_short_selling,
            guaranteed_stop_loss=proto.guaranteed_stop_loss,
            sl_distance=proto.sl_distance if proto.sl_distance else 0,
            tp_distance=proto.tp_distance if proto.tp_distance else 0,
            schedule_timezone=proto.schedule_time_zone or "",
            measurement_units=proto.measurement_units or "",
        )
