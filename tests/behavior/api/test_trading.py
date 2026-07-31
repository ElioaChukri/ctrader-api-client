"""Placing, amending and reading orders and positions."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ctrader_api_client._internal.proto import (
    ProtoOAAmendOrderReq,
    ProtoOAAmendPositionSLTPReq,
    ProtoOAApplicationAuthRes,
    ProtoOACancelOrderReq,
    ProtoOAClosePositionReq,
    ProtoOADeal,
    ProtoOADealListByPositionIdReq,
    ProtoOADealListByPositionIdRes,
    ProtoOADealListReq,
    ProtoOADealListRes,
    ProtoOADealStatus,
    ProtoOAExecutionEvent,
    ProtoOAExecutionType,
    ProtoOAGetPositionUnrealizedPnLReq,
    ProtoOAGetPositionUnrealizedPnLRes,
    ProtoOANewOrderReq,
    ProtoOAOrder,
    ProtoOAOrderErrorEvent,
    ProtoOAOrderListReq,
    ProtoOAOrderListRes,
    ProtoOAOrderStatus,
    ProtoOAOrderType,
    ProtoOAPosition,
    ProtoOAPositionStatus,
    ProtoOAPositionUnrealizedPnL,
    ProtoOAReconcileReq,
    ProtoOAReconcileRes,
    ProtoOATradeData,
    ProtoOATradeSide,
)
from ctrader_api_client.api import TradingAPI
from ctrader_api_client.enums import ExecutionType, OrderSide, OrderType
from ctrader_api_client.exceptions import APIError
from ctrader_api_client.models import (
    AmendOrderRequest,
    AmendPositionRequest,
    ClosePositionRequest,
    NewOrderRequest,
)

from ...harness import StubProtocol, factories


ORDER_ID = 500
POSITION_ID = 900
EXECUTED_AT_MS = 1_700_000_000_000
EXECUTED_AT = datetime.fromtimestamp(EXECUTED_AT_MS / 1000, tz=UTC)


def trade_data(side: ProtoOATradeSide = ProtoOATradeSide.BUY, volume: int = 100_000) -> ProtoOATradeData:
    return ProtoOATradeData(
        symbol_id=factories.SYMBOL_ID,
        volume=volume,
        trade_side=side,
        open_timestamp=EXECUTED_AT_MS,
    )


def order(
    order_id: int = ORDER_ID,
    order_type: ProtoOAOrderType = ProtoOAOrderType.MARKET,
    order_status: ProtoOAOrderStatus = ProtoOAOrderStatus.ORDER_STATUS_FILLED,
    side: ProtoOATradeSide = ProtoOATradeSide.BUY,
) -> ProtoOAOrder:
    return ProtoOAOrder(
        order_id=order_id,
        trade_data=trade_data(side=side),
        order_type=order_type,
        order_status=order_status,
        executed_volume=100_000,
        execution_price=1.0855,
    )


def filled(**overrides: object) -> ProtoOAExecutionEvent:
    """A fill: order, position and deal all present."""
    fields: dict[str, object] = {
        "ctid_trader_account_id": factories.ACCOUNT_ID,
        "execution_type": ProtoOAExecutionType.ORDER_FILLED,
        "order": order(),
        "position": ProtoOAPosition(position_id=POSITION_ID),
        "deal": ProtoOADeal(
            deal_id=1,
            filled_volume=100_000,
            execution_price=1.0855,
            execution_timestamp=EXECUTED_AT_MS,
        ),
    }
    fields.update(overrides)
    return ProtoOAExecutionEvent(**fields)  # type: ignore[arg-type]


def market_order() -> NewOrderRequest:
    return NewOrderRequest(
        symbol_id=factories.SYMBOL_ID,
        side=OrderSide.BUY,
        volume=100_000,
        order_type=OrderType.MARKET,
    )


async def test_a_placed_order_reports_its_execution(trading: TradingAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOANewOrderReq, filled())

    execution = await trading.place_order(factories.ACCOUNT_ID, market_order())

    assert execution.execution_type is ExecutionType.ORDER_FILLED
    assert execution.order_id == ORDER_ID
    assert execution.position_id == POSITION_ID
    assert execution.symbol_id == factories.SYMBOL_ID
    assert execution.side is OrderSide.BUY
    assert execution.filled_volume == 100_000
    assert execution.fill_price == Decimal("1.0855")
    assert execution.timestamp == EXECUTED_AT


async def test_the_order_request_carries_the_account_and_symbol(
    trading: TradingAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOANewOrderReq, filled())

    await trading.place_order(factories.ACCOUNT_ID, market_order())

    request = protocol.only_sent(ProtoOANewOrderReq)
    assert request.ctid_trader_account_id == factories.ACCOUNT_ID
    assert request.symbol_id == factories.SYMBOL_ID
    assert request.volume == 100_000


async def test_an_accepted_order_has_no_position_yet(trading: TradingAPI, protocol: StubProtocol) -> None:
    """A pending order must not look like it opened a position."""
    protocol.respond(
        ProtoOANewOrderReq,
        ProtoOAExecutionEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            execution_type=ProtoOAExecutionType.ORDER_ACCEPTED,
            order=order(order_type=ProtoOAOrderType.LIMIT, order_status=ProtoOAOrderStatus.ORDER_STATUS_ACCEPTED),
        ),
    )

    execution = await trading.place_order(factories.ACCOUNT_ID, market_order())

    assert execution.execution_type is ExecutionType.ORDER_ACCEPTED
    assert execution.position_id is None
    assert execution.filled_volume is None
    assert execution.fill_price is None


async def test_a_rejected_order_reports_the_rejection(trading: TradingAPI, protocol: StubProtocol) -> None:
    protocol.respond(
        ProtoOANewOrderReq,
        ProtoOAExecutionEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            execution_type=ProtoOAExecutionType.ORDER_REJECTED,
            order=order(order_status=ProtoOAOrderStatus.ORDER_STATUS_REJECTED),
            error_code="NOT_ENOUGH_MONEY",
        ),
    )

    execution = await trading.place_order(factories.ACCOUNT_ID, market_order())

    assert execution.execution_type is ExecutionType.ORDER_REJECTED
    assert execution.error_code == "NOT_ENOUGH_MONEY"


async def test_an_order_error_is_raised_rather_than_returned(
    trading: TradingAPI,
    protocol: StubProtocol,
) -> None:
    """A caller that never checks the returned event would otherwise trade blind."""
    protocol.respond(
        ProtoOANewOrderReq,
        ProtoOAOrderErrorEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            error_code="TRADING_BAD_VOLUME",
            order_id=ORDER_ID,
            description="Volume too small",
        ),
    )

    with pytest.raises(APIError) as exc_info:
        await trading.place_order(factories.ACCOUNT_ID, market_order())

    assert exc_info.value.error_code == "TRADING_BAD_VOLUME"
    assert exc_info.value.description == "Volume too small"
    assert exc_info.value.ctid_trader_account_id == factories.ACCOUNT_ID


async def test_an_unmapped_execution_type_is_an_error(trading: TradingAPI, protocol: StubProtocol) -> None:
    unmapped = filled()
    unmapped.execution_type = 99  # type: ignore[assignment]
    protocol.respond(ProtoOANewOrderReq, unmapped)

    with pytest.raises(APIError) as exc_info:
        await trading.place_order(factories.ACCOUNT_ID, market_order())

    assert exc_info.value.error_code == "UNKNOWN_EXECUTION_TYPE"


async def test_an_unexpected_order_reply_is_an_error(trading: TradingAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOANewOrderReq, ProtoOAApplicationAuthRes())

    with pytest.raises(APIError) as exc_info:
        await trading.place_order(factories.ACCOUNT_ID, market_order())

    assert exc_info.value.error_code == "UNEXPECTED_RESPONSE"


async def test_an_amended_order_reports_its_execution(trading: TradingAPI, protocol: StubProtocol) -> None:
    protocol.respond(
        ProtoOAAmendOrderReq,
        filled(execution_type=ProtoOAExecutionType.ORDER_REPLACED),
    )

    execution = await trading.amend_order(
        factories.ACCOUNT_ID,
        AmendOrderRequest(order_id=ORDER_ID, limit_price=Decimal("1.0800")),
    )

    assert execution.execution_type is ExecutionType.ORDER_REPLACED
    assert protocol.only_sent(ProtoOAAmendOrderReq).order_id == ORDER_ID


async def test_a_cancelled_order_reports_its_execution(trading: TradingAPI, protocol: StubProtocol) -> None:
    protocol.respond(
        ProtoOACancelOrderReq,
        filled(execution_type=ProtoOAExecutionType.ORDER_CANCELLED),
    )

    execution = await trading.cancel_order(factories.ACCOUNT_ID, ORDER_ID)

    assert execution.execution_type is ExecutionType.ORDER_CANCELLED
    request = protocol.only_sent(ProtoOACancelOrderReq)
    assert (request.ctid_trader_account_id, request.order_id) == (factories.ACCOUNT_ID, ORDER_ID)


async def test_cancelling_an_unknown_order_raises(trading: TradingAPI, protocol: StubProtocol) -> None:
    protocol.respond(
        ProtoOACancelOrderReq,
        ProtoOAOrderErrorEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            error_code="ORDER_NOT_FOUND",
            order_id=ORDER_ID,
        ),
    )

    with pytest.raises(APIError) as exc_info:
        await trading.cancel_order(factories.ACCOUNT_ID, ORDER_ID)

    assert exc_info.value.error_code == "ORDER_NOT_FOUND"


async def test_a_closed_position_reports_its_execution(trading: TradingAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOAClosePositionReq, filled())

    execution = await trading.close_position(
        factories.ACCOUNT_ID,
        ClosePositionRequest(position_id=POSITION_ID, volume=100_000),
    )

    assert execution.position_id == POSITION_ID
    request = protocol.only_sent(ProtoOAClosePositionReq)
    assert (request.position_id, request.volume) == (POSITION_ID, 100_000)


async def test_an_amended_position_reports_its_execution(trading: TradingAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOAAmendPositionSLTPReq, filled())

    execution = await trading.amend_position(
        factories.ACCOUNT_ID,
        AmendPositionRequest(
            position_id=POSITION_ID,
            stop_loss=Decimal("1.0800"),
            take_profit=Decimal("1.0900"),
        ),
    )

    assert execution.position_id == POSITION_ID
    request = protocol.only_sent(ProtoOAAmendPositionSLTPReq)
    assert request.position_id == POSITION_ID
    assert request.stop_loss == 1.0800


async def test_open_positions_are_returned(trading: TradingAPI, protocol: StubProtocol) -> None:
    protocol.respond(
        ProtoOAReconcileReq,
        ProtoOAReconcileRes(
            position=[
                ProtoOAPosition(
                    position_id=POSITION_ID,
                    trade_data=trade_data(),
                    position_status=ProtoOAPositionStatus.POSITION_STATUS_OPEN,
                    price=1.0855,
                    money_digits=2,
                ),
            ]
        ),
    )

    positions = await trading.get_open_positions(factories.ACCOUNT_ID)

    assert [p.position_id for p in positions] == [POSITION_ID]
    assert positions[0].entry_price == Decimal("1.0855")


async def test_no_open_positions_is_an_empty_list(trading: TradingAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOAReconcileReq, ProtoOAReconcileRes(position=[]))

    assert await trading.get_open_positions(factories.ACCOUNT_ID) == []


async def test_orders_in_a_time_range_are_returned(trading: TradingAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOAOrderListReq, ProtoOAOrderListRes(order=[order(), order(order_id=501)]))

    orders = await trading.get_orders(
        factories.ACCOUNT_ID,
        from_timestamp=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
        to_timestamp=datetime(2023, 11, 15, 22, 13, 20, tzinfo=UTC),
    )

    assert [o.order_id for o in orders] == [ORDER_ID, 501]


async def test_the_order_history_request_carries_the_time_range(
    trading: TradingAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOAOrderListReq, ProtoOAOrderListRes(order=[]))

    await trading.get_orders(
        factories.ACCOUNT_ID,
        from_timestamp=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
        to_timestamp=datetime(2023, 11, 15, 22, 13, 20, tzinfo=UTC),
    )

    request = protocol.only_sent(ProtoOAOrderListReq)
    assert request.from_timestamp == EXECUTED_AT_MS
    assert request.to_timestamp == EXECUTED_AT_MS + 86_400_000


async def test_only_pending_orders_are_reported_as_pending(
    trading: TradingAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(
        ProtoOAOrderListReq,
        ProtoOAOrderListRes(
            order=[
                order(order_id=500, order_status=ProtoOAOrderStatus.ORDER_STATUS_FILLED),
                order(
                    order_id=501,
                    order_type=ProtoOAOrderType.LIMIT,
                    order_status=ProtoOAOrderStatus.ORDER_STATUS_ACCEPTED,
                ),
            ]
        ),
    )

    pending = await trading.get_pending_orders(factories.ACCOUNT_ID)

    assert [o.order_id for o in pending] == [501]


async def test_deals_for_a_position_are_returned(trading: TradingAPI, protocol: StubProtocol) -> None:
    protocol.respond(
        ProtoOADealListByPositionIdReq,
        ProtoOADealListByPositionIdRes(
            deal=[
                ProtoOADeal(
                    deal_id=1,
                    order_id=ORDER_ID,
                    position_id=POSITION_ID,
                    volume=100_000,
                    filled_volume=100_000,
                    symbol_id=factories.SYMBOL_ID,
                    trade_side=ProtoOATradeSide.BUY,
                    deal_status=ProtoOADealStatus.FILLED,
                    execution_price=1.0855,
                    execution_timestamp=EXECUTED_AT_MS,
                    create_timestamp=EXECUTED_AT_MS,
                )
            ]
        ),
    )

    deals = await trading.get_deals_by_position_id(factories.ACCOUNT_ID, POSITION_ID)

    assert [d.deal_id for d in deals] == [1]
    assert deals[0].position_id == POSITION_ID
    request = protocol.only_sent(ProtoOADealListByPositionIdReq)
    assert request.position_id == POSITION_ID


async def test_the_deal_history_request_carries_the_time_range(
    trading: TradingAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOADealListReq, ProtoOADealListRes(deal=[]))

    await trading.get_deals(
        factories.ACCOUNT_ID,
        from_timestamp=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
        to_timestamp=datetime(2023, 11, 15, 22, 13, 20, tzinfo=UTC),
    )

    request = protocol.only_sent(ProtoOADealListReq)
    assert request.from_timestamp == EXECUTED_AT_MS
    assert request.to_timestamp == EXECUTED_AT_MS + 86_400_000


async def test_unrealized_pnl_is_scaled_by_money_digits(
    trading: TradingAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(
        ProtoOAGetPositionUnrealizedPnLReq,
        ProtoOAGetPositionUnrealizedPnLRes(
            position_unrealized_pn_l=[
                ProtoOAPositionUnrealizedPnL(
                    position_id=POSITION_ID,
                    gross_unrealized_pn_l=12_345,
                    net_unrealized_pn_l=12_000,
                )
            ],
            money_digits=2,
        ),
    )

    pnl = await trading.get_unrealized_pnl_per_position(factories.ACCOUNT_ID)

    assert pnl[0].position_id == POSITION_ID
    assert pnl[0].gross_unrealized_pnl == Decimal("123.45")
    assert pnl[0].net_unrealized_pnl == Decimal(120)


async def test_unrealized_pnl_honours_a_different_money_scale(
    trading: TradingAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(
        ProtoOAGetPositionUnrealizedPnLReq,
        ProtoOAGetPositionUnrealizedPnLRes(
            position_unrealized_pn_l=[
                ProtoOAPositionUnrealizedPnL(
                    position_id=POSITION_ID,
                    gross_unrealized_pn_l=12_345,
                    net_unrealized_pn_l=12_000,
                )
            ],
            money_digits=5,
        ),
    )

    pnl = await trading.get_unrealized_pnl_per_position(factories.ACCOUNT_ID)

    assert pnl[0].gross_unrealized_pnl == Decimal("0.12345")


async def test_an_unexpected_position_list_reply_is_an_error(
    trading: TradingAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOAReconcileReq, ProtoOAApplicationAuthRes())

    with pytest.raises(APIError) as exc_info:
        await trading.get_open_positions(factories.ACCOUNT_ID)

    assert exc_info.value.error_code == "UNEXPECTED_RESPONSE"


async def test_an_unexpected_deal_list_reply_is_an_error(trading: TradingAPI, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOADealListReq, ProtoOAApplicationAuthRes())

    with pytest.raises(APIError) as exc_info:
        await trading.get_deals(
            factories.ACCOUNT_ID,
            from_timestamp=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
            to_timestamp=datetime(2023, 11, 15, 22, 13, 20, tzinfo=UTC),
        )

    assert exc_info.value.error_code == "UNEXPECTED_RESPONSE"
