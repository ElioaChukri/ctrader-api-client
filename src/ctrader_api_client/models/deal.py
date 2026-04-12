from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from .._internal.proto import ProtoOADealStatus
from ..enums import DealStatus, OrderSide
from ._base import FrozenModel


if TYPE_CHECKING:
    from .._internal.proto import ProtoOAClosePositionDetail, ProtoOADeal
    from .symbol import Symbol


def _timestamp_to_datetime(timestamp_ms: int) -> datetime:
    """Convert millisecond timestamp to datetime."""
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)


_DEAL_STATUS_MAP: dict[int, DealStatus] = {
    ProtoOADealStatus.FILLED: DealStatus.FILLED,
    ProtoOADealStatus.PARTIALLY_FILLED: DealStatus.PARTIALLY_FILLED,
    ProtoOADealStatus.REJECTED: DealStatus.REJECTED,
    ProtoOADealStatus.INTERNALLY_REJECTED: DealStatus.INTERNALLY_REJECTED,
    ProtoOADealStatus.ERROR: DealStatus.ERROR,
    ProtoOADealStatus.MISSED: DealStatus.MISSED,
}


class CloseDetail(FrozenModel):
    """Details about position closure from a deal.

    Present only when a deal results in closing (fully or partially)
    a position.

    Attributes:
        entry_price: Original entry price of the position.
        closed_volume: Volume that was closed.
        gross_profit: Gross profit/loss (raw integer).
        swap: Swap charged (raw integer).
        commission: Commission charged (raw integer).
        balance: Account balance after close (raw integer).
        money_digits: Decimal places for monetary values.
        pnl_conversion_fee: Fee for P&L currency conversion (raw integer).
        quote_to_deposit_rate: Conversion rate from quote to deposit currency.
        balance_version: Version number for balance updates.
    """

    entry_price: float
    closed_volume: int
    gross_profit: int
    swap: int
    commission: int
    balance: int
    money_digits: int
    pnl_conversion_fee: int = 0
    quote_to_deposit_rate: float | None = None
    balance_version: int | None = None

    def get_gross_profit(self) -> Decimal:
        """Get gross profit as Decimal.

        Returns:
            Gross profit divided by 10^money_digits.
        """
        return Decimal(self.gross_profit) / Decimal(10**self.money_digits)

    def get_net_profit(self) -> Decimal:
        """Get net profit (gross - swap - commission - fee) as Decimal.

        Returns:
            Net profit divided by 10^money_digits.
        """
        net = self.gross_profit - self.swap - self.commission - self.pnl_conversion_fee
        return Decimal(net) / Decimal(10**self.money_digits)

    def get_swap(self) -> Decimal:
        """Get swap as Decimal.

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

    @classmethod
    def from_proto(cls, proto: ProtoOAClosePositionDetail) -> CloseDetail:
        """Create CloseDetail from proto message.

        Args:
            proto: The proto message to convert.

        Returns:
            A new CloseDetail instance.
        """
        return cls(
            entry_price=proto.entry_price,
            closed_volume=proto.closed_volume,
            gross_profit=proto.gross_profit,
            swap=proto.swap,
            commission=proto.commission,
            balance=proto.balance,
            money_digits=proto.money_digits if proto.money_digits else 2,
            pnl_conversion_fee=proto.pnl_conversion_fee if proto.pnl_conversion_fee else 0,
            quote_to_deposit_rate=proto.quote_to_deposit_conversion_rate
            if proto.quote_to_deposit_conversion_rate
            else None,
            balance_version=proto.balance_version if proto.balance_version else None,
        )


class Deal(FrozenModel):
    """A trade execution (deal).

    Represents a single execution that fills an order. An order may have
    multiple deals if it's filled in parts.

    Attributes:
        deal_id: Unique deal identifier.
        order_id: The order that was executed.
        position_id: The position affected by this deal.
        symbol_id: The symbol traded.
        side: Trade direction (BUY/SELL).
        volume: Requested volume in cents.
        filled_volume: Actually filled volume in cents.
        execution_price: Price at which the deal was executed.
        execution_timestamp: When the deal was executed.
        status: Deal status.
        commission: Commission charged (raw integer).
        money_digits: Decimal places for monetary values.
        create_timestamp: When the deal was created.
        last_update_timestamp: When the deal was last updated.
        margin_rate: Margin rate for the deal.
        base_to_usd_rate: Conversion rate from base currency to USD.
        close_detail: Details if this deal closed a position, or None.
    """

    deal_id: int
    order_id: int
    position_id: int
    symbol_id: int
    side: OrderSide
    volume: int
    filled_volume: int
    execution_price: float
    execution_timestamp: datetime
    status: DealStatus
    commission: int
    money_digits: int

    # Optional
    create_timestamp: datetime | None = None
    last_update_timestamp: datetime | None = None
    margin_rate: float | None = None
    base_to_usd_rate: float | None = None
    close_detail: CloseDetail | None = None

    def get_execution_price(self, symbol: Symbol) -> Decimal:
        """Get execution price as Decimal.

        Args:
            symbol: Symbol for price precision.

        Returns:
            Execution price with correct decimal places.
        """
        return Decimal(str(self.execution_price)).quantize(Decimal(10) ** -symbol.digits)

    def get_commission(self) -> Decimal:
        """Get commission as Decimal.

        Returns:
            Commission divided by 10^money_digits.
        """
        return Decimal(self.commission) / Decimal(10**self.money_digits)

    def get_volume_in_lots(self, symbol: Symbol) -> Decimal:
        """Get filled volume in lots.

        Args:
            symbol: Symbol for lot conversion.

        Returns:
            Volume in lots.
        """
        return symbol.volume_to_lots(self.filled_volume)

    @property
    def is_closing_deal(self) -> bool:
        """Whether this deal closed (or partially closed) a position."""
        return self.close_detail is not None

    @classmethod
    def from_proto(cls, proto: ProtoOADeal) -> Deal:
        """Create Deal from proto message.

        Args:
            proto: The proto message to convert.

        Returns:
            A new Deal instance.
        """
        close_detail = None
        if proto.close_position_detail:
            close_detail = CloseDetail.from_proto(proto.close_position_detail)

        # Determine side
        side = OrderSide.BUY if proto.trade_side == 1 else OrderSide.SELL

        return cls(
            deal_id=proto.deal_id,
            order_id=proto.order_id,
            position_id=proto.position_id,
            symbol_id=proto.symbol_id,
            side=side,
            volume=proto.volume,
            filled_volume=proto.filled_volume,
            execution_price=proto.execution_price,
            execution_timestamp=_timestamp_to_datetime(proto.execution_timestamp),
            status=_DEAL_STATUS_MAP.get(proto.deal_status, DealStatus.FILLED),
            commission=proto.commission if proto.commission else 0,
            money_digits=proto.money_digits if proto.money_digits else 2,
            create_timestamp=_timestamp_to_datetime(proto.create_timestamp) if proto.create_timestamp else None,
            last_update_timestamp=(
                _timestamp_to_datetime(proto.utc_last_update_timestamp) if proto.utc_last_update_timestamp else None
            ),
            margin_rate=proto.margin_rate if proto.margin_rate else None,
            base_to_usd_rate=proto.base_to_usd_conversion_rate if proto.base_to_usd_conversion_rate else None,
            close_detail=close_detail,
        )
