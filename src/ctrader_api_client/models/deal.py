from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .._internal.proto import ProtoOADealStatus
from ..enums import DealStatus, OrderSide
from ._base import FrozenModel


if TYPE_CHECKING:
    from .._internal.proto import ProtoOAClosePositionDetail, ProtoOADeal


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
        closed_volume: Volume that was closed in cents.
        gross_profit: Gross profit/loss.
        swap: Swap charged.
        commission: Commission charged.
        balance: Account balance after close.
        pnl_conversion_fee: Fee for P&L currency conversion.
        quote_to_deposit_rate: Conversion rate from quote to deposit currency.
        balance_version: Version number for balance updates.
    """

    entry_price: float
    closed_volume: int
    gross_profit: float
    swap: float
    commission: float
    balance: float
    pnl_conversion_fee: float = 0
    quote_to_deposit_rate: float | None = None
    balance_version: int | None = None

    @classmethod
    def from_proto(cls, proto: ProtoOAClosePositionDetail) -> CloseDetail:
        """Create CloseDetail from proto message.

        Args:
            proto: The proto message to convert.

        Returns:
            A new CloseDetail instance.
        """
        money_digits = proto.money_digits if proto.money_digits else 2
        divisor = 10**money_digits
        return cls(
            entry_price=proto.entry_price,
            closed_volume=proto.closed_volume,
            gross_profit=proto.gross_profit / divisor,
            swap=proto.swap / divisor,
            commission=proto.commission / divisor,
            balance=proto.balance / divisor,
            pnl_conversion_fee=proto.pnl_conversion_fee / divisor if proto.pnl_conversion_fee else 0,
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
        commission: Commission charged.
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
    commission: float

    # Optional
    create_timestamp: datetime | None = None
    last_update_timestamp: datetime | None = None
    margin_rate: float | None = None
    base_to_usd_rate: float | None = None
    close_detail: CloseDetail | None = None

    @property
    def is_closing_deal(self) -> bool:
        """Whether this deal closed (or partially closed) a position."""
        if self.close_detail is not None:
            return self.close_detail.balance > 0
        else:
            return False

    @classmethod
    def from_proto(cls, proto: ProtoOADeal) -> Deal:
        """Create Deal from proto message.

        Args:
            proto: The proto message to convert.

        Returns:
            A new Deal instance.
        """
        close_detail = None
        # This check is necessary because close_position_detail is always present in the proto,
        # but with zero balance if it's not a closing deal.
        if proto.close_position_detail and proto.close_position_detail.balance > 0:
            close_detail = CloseDetail.from_proto(proto.close_position_detail)

        # Determine side
        side = OrderSide.BUY if proto.trade_side == 1 else OrderSide.SELL

        money_digits = proto.money_digits if proto.money_digits else 2
        divisor = 10**money_digits
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
            commission=proto.commission / divisor if proto.commission else 0,
            create_timestamp=_timestamp_to_datetime(proto.create_timestamp) if proto.create_timestamp else None,
            last_update_timestamp=(
                _timestamp_to_datetime(proto.utc_last_update_timestamp) if proto.utc_last_update_timestamp else None
            ),
            margin_rate=proto.margin_rate if proto.margin_rate else None,
            base_to_usd_rate=proto.base_to_usd_conversion_rate if proto.base_to_usd_conversion_rate else None,
            close_detail=close_detail,
        )
