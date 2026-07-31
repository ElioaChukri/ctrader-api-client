"""Translation of trading records from the wire into domain models.

Money arrives as an integer scaled by `money_digits`, timestamps arrive in
milliseconds, and "not set" is encoded as zero. Those three rules are where
silent corruption would hide.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ctrader_api_client._internal.proto import (
    ProtoOAClosePositionDetail,
    ProtoOACtidTraderAccount,
    ProtoOADeal,
    ProtoOADealStatus,
    ProtoOAOrder,
    ProtoOAOrderStatus,
    ProtoOAOrderType,
    ProtoOAPosition,
    ProtoOAPositionStatus,
    ProtoOATradeData,
    ProtoOATrader,
    ProtoOATradeSide,
)
from ctrader_api_client.enums import AccountType, DealStatus, OrderSide, OrderStatus, OrderType, PositionStatus
from ctrader_api_client.models import Account, AccountSummary, Deal, Order, Position


BUY = ProtoOATradeSide.BUY
SELL = ProtoOATradeSide.SELL
EXECUTED_AT_MS = 1_700_000_000_000


def trade_data(**overrides: object) -> ProtoOATradeData:
    settings: dict[str, object] = {
        "symbol_id": 270,
        "volume": 100_000,
        "trade_side": BUY,
        "open_timestamp": EXECUTED_AT_MS,
    }
    settings.update(overrides)
    return ProtoOATradeData(**settings)  # type: ignore[arg-type]


def test_a_position_reports_its_trade_details() -> None:
    position = Position.from_proto(
        ProtoOAPosition(
            position_id=1001,
            trade_data=trade_data(label="strategy-a", comment="entry"),
            price=1.10500,
            position_status=ProtoOAPositionStatus.POSITION_STATUS_OPEN,
            money_digits=2,
        )
    )

    assert position.position_id == 1001
    assert position.symbol_id == 270
    assert position.volume == 100_000
    assert position.side == OrderSide.BUY
    assert position.entry_price == Decimal("1.105")
    assert position.status == PositionStatus.OPEN
    assert position.open_timestamp == datetime.fromtimestamp(EXECUTED_AT_MS / 1000, tz=UTC)
    assert (position.label, position.comment) == ("strategy-a", "entry")


def test_a_sell_position_is_reported_as_a_sell() -> None:
    position = Position.from_proto(ProtoOAPosition(position_id=1, trade_data=trade_data(trade_side=SELL)))

    assert position.side == OrderSide.SELL


def test_position_money_is_scaled_by_the_money_digits() -> None:
    position = Position.from_proto(
        ProtoOAPosition(
            position_id=1,
            trade_data=trade_data(),
            money_digits=2,
            swap=-125,
            commission=-70,
            used_margin=1_000_00,
        )
    )

    assert position.swap == Decimal("-1.25")
    assert position.commission == Decimal("-0.7")
    assert position.used_margin == Decimal(1000)


def test_position_money_honours_a_different_scale() -> None:
    """Some accounts quote money to more places; assuming cents would inflate everything."""
    position = Position.from_proto(
        ProtoOAPosition(position_id=1, trade_data=trade_data(), money_digits=5, swap=-125_000)
    )

    assert position.swap == Decimal("-1.25")


def test_position_levels_left_unset_are_reported_as_absent() -> None:
    position = Position.from_proto(ProtoOAPosition(position_id=1, trade_data=trade_data()))

    assert position.stop_loss is None
    assert position.take_profit is None
    assert position.close_timestamp is None
    assert position.last_update_timestamp is None


def test_a_closed_position_reports_when_it_closed() -> None:
    position = Position.from_proto(
        ProtoOAPosition(
            position_id=1,
            trade_data=trade_data(close_timestamp=EXECUTED_AT_MS),
            position_status=ProtoOAPositionStatus.POSITION_STATUS_CLOSED,
        )
    )

    assert position.status == PositionStatus.CLOSED
    assert position.close_timestamp == datetime.fromtimestamp(EXECUTED_AT_MS / 1000, tz=UTC)


def test_an_order_reports_its_type_status_and_levels() -> None:
    order = Order.from_proto(
        ProtoOAOrder(
            order_id=2001,
            trade_data=trade_data(),
            order_type=ProtoOAOrderType.LIMIT,
            order_status=ProtoOAOrderStatus.ORDER_STATUS_ACCEPTED,
            limit_price=1.10000,
            stop_loss=1.09000,
            take_profit=1.12000,
        )
    )

    assert order.order_id == 2001
    assert order.order_type == OrderType.LIMIT
    assert order.status == OrderStatus.ACCEPTED
    assert order.limit_price == Decimal("1.1")
    assert order.stop_loss == Decimal("1.09")
    assert order.take_profit == Decimal("1.12")


@pytest.mark.parametrize(
    ("proto_status", "expected", "pending", "filled"),
    [
        (ProtoOAOrderStatus.ORDER_STATUS_ACCEPTED, OrderStatus.ACCEPTED, True, False),
        (ProtoOAOrderStatus.ORDER_STATUS_FILLED, OrderStatus.FILLED, False, True),
        (ProtoOAOrderStatus.ORDER_STATUS_REJECTED, OrderStatus.REJECTED, False, False),
        (ProtoOAOrderStatus.ORDER_STATUS_CANCELLED, OrderStatus.CANCELLED, False, False),
        (ProtoOAOrderStatus.ORDER_STATUS_EXPIRED, OrderStatus.EXPIRED, False, False),
    ],
)
def test_order_status_drives_the_pending_and_filled_answers(
    proto_status: ProtoOAOrderStatus,
    expected: OrderStatus,
    pending: bool,
    filled: bool,
) -> None:
    order = Order.from_proto(ProtoOAOrder(order_id=1, trade_data=trade_data(), order_status=proto_status))

    assert order.status == expected
    assert order.is_pending is pending
    assert order.is_filled is filled


def test_order_fields_left_unset_are_reported_as_absent() -> None:
    order = Order.from_proto(ProtoOAOrder(order_id=1, trade_data=trade_data()))

    assert order.limit_price is None
    assert order.stop_price is None
    assert order.execution_price is None
    assert order.position_id is None
    assert order.expiration_timestamp is None
    assert order.executed_volume == 0


def test_a_deal_reports_what_was_executed() -> None:
    deal = Deal.from_proto(
        ProtoOADeal(
            deal_id=3001,
            order_id=2001,
            position_id=1001,
            symbol_id=270,
            trade_side=BUY,
            volume=100_000,
            filled_volume=100_000,
            execution_price=1.10500,
            execution_timestamp=EXECUTED_AT_MS,
            deal_status=ProtoOADealStatus.FILLED,
            money_digits=2,
            commission=-70,
        )
    )

    assert deal.deal_id == 3001
    assert deal.side == OrderSide.BUY
    assert deal.filled_volume == 100_000
    assert deal.execution_price == Decimal("1.105")
    assert deal.execution_timestamp == datetime.fromtimestamp(EXECUTED_AT_MS / 1000, tz=UTC)
    assert deal.status == DealStatus.FILLED
    assert deal.commission == Decimal("-0.7")


def test_a_deal_that_closed_a_position_carries_the_close_details() -> None:
    deal = Deal.from_proto(
        ProtoOADeal(
            deal_id=1,
            execution_timestamp=EXECUTED_AT_MS,
            trade_side=SELL,
            money_digits=2,
            close_position_detail=ProtoOAClosePositionDetail(
                entry_price=1.10000,
                closed_volume=100_000,
                gross_profit=5_00,
                swap=-1_25,
                commission=-70,
                balance=10_500_00,
                money_digits=2,
            ),
        )
    )

    assert deal.is_closing_deal
    assert deal.close_detail is not None
    assert deal.close_detail.gross_profit == Decimal(5)
    assert deal.close_detail.balance == Decimal(10500)
    assert deal.close_detail.closed_volume == 100_000


def test_an_opening_deal_has_no_close_details() -> None:
    """The proto always carries a close block; a zero balance means it is not a close."""
    deal = Deal.from_proto(
        ProtoOADeal(
            deal_id=1,
            execution_timestamp=EXECUTED_AT_MS,
            trade_side=BUY,
            close_position_detail=ProtoOAClosePositionDetail(balance=0),
        )
    )

    assert deal.close_detail is None
    assert not deal.is_closing_deal


def test_an_account_reports_its_balance_at_the_stated_scale() -> None:
    account = Account.from_proto(
        ProtoOATrader(
            ctid_trader_account_id=12345678,
            trader_login=17091452,
            balance=1_234_567,
            money_digits=2,
            leverage_in_cents=10_000,
            broker_name="Test Broker",
            deposit_asset_id=1,
        )
    )

    assert account.balance == Decimal("12345.67")
    assert account.account_id == 12345678
    assert account.trader_login == 17091452
    assert account.broker_name == "Test Broker"


def test_leverage_is_presented_as_a_ratio() -> None:
    account = Account.from_proto(ProtoOATrader(ctid_trader_account_id=1, leverage_in_cents=10_000))

    assert account.get_leverage() == "1:100"


def test_an_unmapped_account_type_falls_back_to_hedged() -> None:
    """An account type the client has never seen must not stop the account loading."""
    account = Account.from_proto(ProtoOATrader(ctid_trader_account_id=1, account_type=999))  # type: ignore[arg-type]

    assert account.account_type == AccountType.HEDGED


def test_account_bonuses_left_unset_are_reported_as_absent() -> None:
    account = Account.from_proto(ProtoOATrader(ctid_trader_account_id=1, money_digits=2))

    assert account.manager_bonus is None
    assert account.ib_bonus is None
    assert account.non_withdrawable_bonus is None
    assert account.max_leverage is None


def test_an_account_listing_entry_identifies_the_account() -> None:
    summary = AccountSummary.from_proto(
        ProtoOACtidTraderAccount(
            ctid_trader_account_id=12345678,
            is_live=True,
            trader_login=17091452,
            broker_title_short="TB",
        )
    )

    assert summary.account_id == 12345678
    assert summary.is_live is True
    assert summary.trader_login == 17091452
    assert summary.broker_name == "TB"
    assert summary.last_closing_deal_timestamp is None
