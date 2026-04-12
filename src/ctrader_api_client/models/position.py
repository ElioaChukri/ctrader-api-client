from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from .._internal.proto import ProtoOAOrderTriggerMethod, ProtoOAPositionStatus
from ..enums import OrderSide, PositionStatus, StopTriggerMethod
from ._base import FrozenModel


if TYPE_CHECKING:
    from .._internal.proto import ProtoOAPosition
    from .symbol import Symbol


def _timestamp_to_datetime(timestamp_ms: int) -> datetime:
    """Convert millisecond timestamp to datetime."""
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)


_POSITION_STATUS_MAP: dict[int, PositionStatus] = {
    ProtoOAPositionStatus.POSITION_STATUS_OPEN: PositionStatus.OPEN,
    ProtoOAPositionStatus.POSITION_STATUS_CLOSED: PositionStatus.CLOSED,
    ProtoOAPositionStatus.POSITION_STATUS_CREATED: PositionStatus.CREATED,
    ProtoOAPositionStatus.POSITION_STATUS_ERROR: PositionStatus.ERROR,
}

_TRIGGER_METHOD_MAP: dict[int, StopTriggerMethod] = {
    ProtoOAOrderTriggerMethod.TRADE: StopTriggerMethod.TRADE,
    ProtoOAOrderTriggerMethod.OPPOSITE: StopTriggerMethod.OPPOSITE,
    ProtoOAOrderTriggerMethod.DOUBLE_TRADE: StopTriggerMethod.DOUBLE_TRADE,
    ProtoOAOrderTriggerMethod.DOUBLE_OPPOSITE: StopTriggerMethod.DOUBLE_OPPOSITE,
}


class Position(FrozenModel):
    """An open or closed trading position.

    Represents a position with all trading details including entry price,
    stop loss, take profit, and P&L information.

    Attributes:
        position_id: Unique position identifier.
        symbol_id: The symbol being traded.
        side: Position direction (BUY/SELL).
        volume: Position volume in cents.
        entry_price: Entry price as float from API.
        status: Current position status.
        open_timestamp: When the position was opened.
        money_digits: Decimal places for monetary values.
        stop_loss: Stop loss price as float, or None if not set.
        take_profit: Take profit price as float, or None if not set.
        trailing_stop_loss: Whether trailing stop is enabled.
        guaranteed_stop_loss: Whether guaranteed stop loss is enabled.
        stop_loss_trigger_method: Method for triggering stop loss.
        swap: Accumulated swap (raw integer).
        commission: Total commission paid (raw integer).
        used_margin: Margin allocated to position (raw integer).
        margin_rate: Margin rate for the position.
        label: User-defined label.
        comment: User-defined comment.
        last_update_timestamp: When the position was last updated.
        close_timestamp: When the position was closed, if applicable.
    """

    position_id: int
    symbol_id: int
    side: OrderSide
    volume: int
    entry_price: float
    status: PositionStatus
    open_timestamp: datetime
    money_digits: int

    # Protection orders
    stop_loss: float | None = None
    take_profit: float | None = None
    trailing_stop_loss: bool = False
    guaranteed_stop_loss: bool = False
    stop_loss_trigger_method: StopTriggerMethod = StopTriggerMethod.TRADE

    # Financial
    swap: int = 0
    commission: int = 0
    used_margin: int = 0
    margin_rate: float | None = None

    # Metadata
    label: str = ""
    comment: str = ""
    last_update_timestamp: datetime | None = None
    close_timestamp: datetime | None = None

    def get_entry_price(self, symbol: Symbol) -> Decimal:
        """Get entry price as Decimal.

        Args:
            symbol: Symbol for price precision.

        Returns:
            Entry price with correct decimal places.
        """
        return Decimal(str(self.entry_price)).quantize(Decimal(10) ** -symbol.digits)

    def get_stop_loss(self, symbol: Symbol) -> Decimal | None:
        """Get stop loss as Decimal.

        Args:
            symbol: Symbol for price precision.

        Returns:
            Stop loss price, or None if not set.
        """
        if self.stop_loss is None:
            return None
        return Decimal(str(self.stop_loss)).quantize(Decimal(10) ** -symbol.digits)

    def get_take_profit(self, symbol: Symbol) -> Decimal | None:
        """Get take profit as Decimal.

        Args:
            symbol: Symbol for price precision.

        Returns:
            Take profit price, or None if not set.
        """
        if self.take_profit is None:
            return None
        return Decimal(str(self.take_profit)).quantize(Decimal(10) ** -symbol.digits)

    def get_swap(self) -> Decimal:
        """Get accumulated swap as Decimal.

        Returns:
            Swap divided by 10^money_digits.
        """
        return Decimal(self.swap) / Decimal(10**self.money_digits)

    def get_commission(self) -> Decimal:
        """Get commission as Decimal.

        Returns:
            Commission divided by 10^money_digits.
        """
        return Decimal(self.commission) / Decimal(10**self.money_digits)

    def get_volume_in_lots(self, symbol: Symbol) -> Decimal:
        """Get volume in lots.

        Args:
            symbol: Symbol for lot conversion.

        Returns:
            Volume in lots.
        """
        return symbol.volume_to_lots(self.volume)

    @classmethod
    def from_proto(cls, proto: ProtoOAPosition) -> Position:
        """Create Position from proto message.

        Args:
            proto: The proto message to convert.

        Returns:
            A new Position instance.
        """
        trade_data = proto.trade_data

        # Determine side from trade_data
        side = OrderSide.BUY
        if trade_data and trade_data.trade_side == 2:
            side = OrderSide.SELL

        # Get open timestamp
        open_ts = datetime.now(UTC)
        if trade_data and trade_data.open_timestamp:
            open_ts = _timestamp_to_datetime(trade_data.open_timestamp)

        return cls(
            position_id=proto.position_id,
            symbol_id=trade_data.symbol_id if trade_data else 0,
            side=side,
            volume=trade_data.volume if trade_data else 0,
            entry_price=proto.price if proto.price else 0.0,
            status=_POSITION_STATUS_MAP.get(proto.position_status, PositionStatus.OPEN),
            open_timestamp=open_ts,
            money_digits=proto.money_digits if proto.money_digits else 2,
            stop_loss=proto.stop_loss if proto.stop_loss else None,
            take_profit=proto.take_profit if proto.take_profit else None,
            trailing_stop_loss=proto.trailing_stop_loss,
            guaranteed_stop_loss=proto.guaranteed_stop_loss,
            stop_loss_trigger_method=_TRIGGER_METHOD_MAP.get(proto.stop_loss_trigger_method, StopTriggerMethod.TRADE),
            swap=proto.swap if proto.swap else 0,
            commission=proto.commission if proto.commission else 0,
            used_margin=proto.used_margin if proto.used_margin else 0,
            margin_rate=proto.margin_rate if proto.margin_rate else None,
            label=trade_data.label if trade_data else "",
            comment=trade_data.comment if trade_data else "",
            last_update_timestamp=(
                _timestamp_to_datetime(proto.utc_last_update_timestamp) if proto.utc_last_update_timestamp else None
            ),
            close_timestamp=(
                _timestamp_to_datetime(trade_data.close_timestamp)
                if trade_data and trade_data.close_timestamp
                else None
            ),
        )
