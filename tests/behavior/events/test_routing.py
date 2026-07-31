"""What a server message turns into by the time a subscriber sees it."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ctrader_api_client._internal.proto import (
    ProtoOAAccountDisconnectEvent,
    ProtoOAAccountsTokenInvalidatedEvent,
    ProtoOAClientDisconnectEvent,
    ProtoOADeal,
    ProtoOADepthEvent,
    ProtoOADepthQuote,
    ProtoOAExecutionEvent,
    ProtoOAExecutionType,
    ProtoOAMarginCall,
    ProtoOAMarginCallTriggerEvent,
    ProtoOAMarginChangedEvent,
    ProtoOANotificationType,
    ProtoOAOrder,
    ProtoOAOrderErrorEvent,
    ProtoOAPosition,
    ProtoOASpotEvent,
    ProtoOASymbolChangedEvent,
    ProtoOATradeData,
    ProtoOATrader,
    ProtoOATraderUpdatedEvent,
    ProtoOATradeSide,
    ProtoOATrailingSLChangedEvent,
    ProtoOATrendbar,
    ProtoOATrendbarPeriod,
)
from ctrader_api_client.enums import ExecutionType, OrderSide
from ctrader_api_client.events import (
    AccountDisconnectEvent,
    ClientDisconnectEvent,
    DepthEvent,
    EventEmitter,
    ExecutionEvent,
    MarginCallTriggerEvent,
    MarginChangeEvent,
    OrderErrorEvent,
    SpotEvent,
    SymbolChangedEvent,
    TokenInvalidatedEvent,
    TraderUpdateEvent,
    TrailingStopChangedEvent,
)

from ...harness import Recorder, StubProtocol, factories


TIMESTAMP_MS = 1_700_000_000_000
TIMESTAMP = datetime.fromtimestamp(TIMESTAMP_MS / 1000, tz=UTC)


def execution(execution_type: ProtoOAExecutionType, **overrides: object) -> ProtoOAExecutionEvent:
    """A minimally populated execution event."""
    fields: dict[str, object] = {
        "ctid_trader_account_id": factories.ACCOUNT_ID,
        "execution_type": execution_type,
    }
    fields.update(overrides)
    return ProtoOAExecutionEvent(**fields)  # type: ignore[arg-type]


def order(side: ProtoOATradeSide = ProtoOATradeSide.BUY, order_id: int = 500) -> ProtoOAOrder:
    return ProtoOAOrder(
        order_id=order_id,
        trade_data=ProtoOATradeData(symbol_id=factories.SYMBOL_ID, volume=100_000, trade_side=side),
    )


async def test_a_spot_event_reaches_a_subscriber(routing: EventEmitter, protocol: StubProtocol) -> None:
    received: Recorder[SpotEvent] = Recorder()
    routing.subscribe(SpotEvent, received)

    await protocol.emit(
        ProtoOASpotEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            symbol_id=factories.SYMBOL_ID,
            bid=108_500,
            ask=108_700,
            timestamp=TIMESTAMP_MS,
        )
    )

    event = received.only
    assert event.account_id == factories.ACCOUNT_ID
    assert event.symbol_id == factories.SYMBOL_ID
    assert event.timestamp == TIMESTAMP


async def test_spot_prices_arrive_as_decimals(routing: EventEmitter, protocol: StubProtocol) -> None:
    received: Recorder[SpotEvent] = Recorder()
    routing.subscribe(SpotEvent, received)

    await protocol.emit(
        ProtoOASpotEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            symbol_id=factories.SYMBOL_ID,
            bid=108_500,
            ask=108_700,
            timestamp=TIMESTAMP_MS,
        )
    )

    assert (received.only.bid, received.only.ask) == (Decimal("1.085"), Decimal("1.087"))


async def test_a_spot_event_without_an_ask_reports_no_ask(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    """A bid-only tick must not be read as a price of zero."""
    received: Recorder[SpotEvent] = Recorder()
    routing.subscribe(SpotEvent, received)

    await protocol.emit(
        ProtoOASpotEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            symbol_id=factories.SYMBOL_ID,
            bid=108_500,
            timestamp=TIMESTAMP_MS,
        )
    )

    assert received.only.bid == Decimal("1.085")
    assert received.only.ask is None


async def test_a_spot_event_carries_its_trendbars(routing: EventEmitter, protocol: StubProtocol) -> None:
    received: Recorder[SpotEvent] = Recorder()
    routing.subscribe(SpotEvent, received)

    await protocol.emit(
        ProtoOASpotEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            symbol_id=factories.SYMBOL_ID,
            bid=108_500,
            timestamp=TIMESTAMP_MS,
            trendbar=[
                ProtoOATrendbar(
                    volume=250,
                    period=ProtoOATrendbarPeriod.M1,
                    low=108_000,
                    delta_open=200,
                    delta_close=500,
                    delta_high=800,
                    utc_timestamp_in_minutes=28_333_333,
                )
            ],
        )
    )

    bar = received.only.trendbar[0]
    assert bar.volume == 250
    assert bar.low == Decimal("1.08")
    assert bar.high == Decimal("1.088")


async def test_a_spot_event_without_trendbars_carries_an_empty_list(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[SpotEvent] = Recorder()
    routing.subscribe(SpotEvent, received)

    await protocol.emit(
        ProtoOASpotEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            symbol_id=factories.SYMBOL_ID,
            bid=108_500,
            timestamp=TIMESTAMP_MS,
        )
    )

    assert received.only.trendbar == []


async def test_a_spot_event_is_filtered_by_symbol(routing: EventEmitter, protocol: StubProtocol) -> None:
    received: Recorder[SpotEvent] = Recorder()
    routing.subscribe(SpotEvent, received, symbol_id=factories.SYMBOL_ID)

    await protocol.emit(
        ProtoOASpotEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            symbol_id=999,
            bid=108_500,
            timestamp=TIMESTAMP_MS,
        )
    )

    assert received.count == 0


@pytest.mark.parametrize(
    ("proto_type", "expected"),
    [
        (ProtoOAExecutionType.ORDER_ACCEPTED, ExecutionType.ORDER_ACCEPTED),
        (ProtoOAExecutionType.ORDER_FILLED, ExecutionType.ORDER_FILLED),
        (ProtoOAExecutionType.ORDER_REPLACED, ExecutionType.ORDER_REPLACED),
        (ProtoOAExecutionType.ORDER_CANCELLED, ExecutionType.ORDER_CANCELLED),
        (ProtoOAExecutionType.ORDER_EXPIRED, ExecutionType.ORDER_EXPIRED),
        (ProtoOAExecutionType.ORDER_REJECTED, ExecutionType.ORDER_REJECTED),
        (ProtoOAExecutionType.ORDER_CANCEL_REJECTED, ExecutionType.ORDER_CANCEL_REJECTED),
        (ProtoOAExecutionType.SWAP, ExecutionType.SWAP),
        (ProtoOAExecutionType.DEPOSIT_WITHDRAW, ExecutionType.DEPOSIT_WITHDRAW),
        (ProtoOAExecutionType.ORDER_PARTIAL_FILL, ExecutionType.ORDER_PARTIAL_FILL),
        (ProtoOAExecutionType.BONUS_DEPOSIT_WITHDRAW, ExecutionType.BONUS_DEPOSIT_WITHDRAW),
    ],
)
async def test_each_execution_type_is_reported(
    routing: EventEmitter,
    protocol: StubProtocol,
    proto_type: ProtoOAExecutionType,
    expected: ExecutionType,
) -> None:
    received: Recorder[ExecutionEvent] = Recorder()
    routing.subscribe(ExecutionEvent, received)

    await protocol.emit(execution(proto_type))

    assert received.only.execution_type is expected


async def test_a_fill_carries_its_order_position_and_deal(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[ExecutionEvent] = Recorder()
    routing.subscribe(ExecutionEvent, received)

    await protocol.emit(
        execution(
            ProtoOAExecutionType.ORDER_FILLED,
            order=order(),
            position=ProtoOAPosition(position_id=900),
            deal=ProtoOADeal(
                filled_volume=100_000,
                execution_price=1.0855,
                execution_timestamp=TIMESTAMP_MS,
            ),
        )
    )

    event = received.only
    assert event.order_id == 500
    assert event.position_id == 900
    assert event.symbol_id == factories.SYMBOL_ID
    assert event.filled_volume == 100_000
    assert event.fill_price == Decimal("1.0855")
    assert event.timestamp == TIMESTAMP


async def test_a_sell_execution_reports_the_sell_side(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[ExecutionEvent] = Recorder()
    routing.subscribe(ExecutionEvent, received)

    await protocol.emit(execution(ProtoOAExecutionType.ORDER_FILLED, order=order(side=ProtoOATradeSide.SELL)))

    assert received.only.side is OrderSide.SELL


async def test_an_execution_without_a_deal_reports_no_fill(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    """An accepted order has not traded yet, so it must not look like a zero-price fill."""
    received: Recorder[ExecutionEvent] = Recorder()
    routing.subscribe(ExecutionEvent, received)

    await protocol.emit(execution(ProtoOAExecutionType.ORDER_ACCEPTED, order=order()))

    event = received.only
    assert event.filled_volume is None
    assert event.fill_price is None
    assert event.position_id is None


async def test_a_rejected_execution_carries_its_error_code(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[ExecutionEvent] = Recorder()
    routing.subscribe(ExecutionEvent, received)

    await protocol.emit(execution(ProtoOAExecutionType.ORDER_REJECTED, order=order(), error_code="NOT_ENOUGH_MONEY"))

    assert received.only.error_code == "NOT_ENOUGH_MONEY"


async def test_an_execution_without_an_error_reports_none(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[ExecutionEvent] = Recorder()
    routing.subscribe(ExecutionEvent, received)

    await protocol.emit(execution(ProtoOAExecutionType.ORDER_FILLED, order=order()))

    assert received.only.error_code is None
    assert received.only.is_server_event is False


async def test_a_server_initiated_execution_is_marked_as_such(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    """A stop-out was not requested by this client and may need different handling."""
    received: Recorder[ExecutionEvent] = Recorder()
    routing.subscribe(ExecutionEvent, received)

    await protocol.emit(execution(ProtoOAExecutionType.ORDER_FILLED, order=order(), is_server_event=True))

    assert received.only.is_server_event is True


async def test_an_unknown_execution_type_is_not_delivered(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    """Guessing at an unmapped execution type could misreport a fill."""
    received: Recorder[ExecutionEvent] = Recorder()
    routing.subscribe(ExecutionEvent, received)

    unmapped = execution(ProtoOAExecutionType.ORDER_FILLED, order=order())
    unmapped.execution_type = 99  # type: ignore[assignment]
    await protocol.emit(unmapped)

    assert received.count == 0


async def test_an_order_error_carries_its_code_and_description(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[OrderErrorEvent] = Recorder()
    routing.subscribe(OrderErrorEvent, received)

    await protocol.emit(
        ProtoOAOrderErrorEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            error_code="NOT_ENOUGH_MONEY",
            order_id=500,
            position_id=900,
            description="Insufficient funds",
        )
    )

    event = received.only
    assert event.account_id == factories.ACCOUNT_ID
    assert event.error_code == "NOT_ENOUGH_MONEY"
    assert event.order_id == 500
    assert event.position_id == 900
    assert event.description == "Insufficient funds"


async def test_an_order_error_without_ids_reports_none(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[OrderErrorEvent] = Recorder()
    routing.subscribe(OrderErrorEvent, received)

    await protocol.emit(ProtoOAOrderErrorEvent(ctid_trader_account_id=factories.ACCOUNT_ID, error_code="BAD_REQUEST"))

    event = received.only
    assert event.order_id is None
    assert event.position_id is None
    assert event.description == ""


async def test_a_trader_update_carries_the_new_balance(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[TraderUpdateEvent] = Recorder()
    routing.subscribe(TraderUpdateEvent, received)

    await protocol.emit(
        ProtoOATraderUpdatedEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            trader=ProtoOATrader(balance=1_000_000, leverage_in_cents=10_000, money_digits=2),
        )
    )

    event = received.only
    assert event.balance == 1_000_000
    assert event.leverage_in_cents == 10_000
    assert event.money_digits == 2


async def test_a_trader_update_without_money_digits_assumes_cents(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[TraderUpdateEvent] = Recorder()
    routing.subscribe(TraderUpdateEvent, received)

    await protocol.emit(
        ProtoOATraderUpdatedEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            trader=ProtoOATrader(balance=1_000_000),
        )
    )

    assert received.only.money_digits == 2
    assert received.only.leverage_in_cents is None


async def test_a_trader_update_without_a_trader_is_not_delivered(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[TraderUpdateEvent] = Recorder()
    routing.subscribe(TraderUpdateEvent, received)

    await protocol.emit(ProtoOATraderUpdatedEvent(ctid_trader_account_id=factories.ACCOUNT_ID))

    assert received.count == 0


async def test_a_margin_change_carries_the_new_margin(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[MarginChangeEvent] = Recorder()
    routing.subscribe(MarginChangeEvent, received)

    await protocol.emit(
        ProtoOAMarginChangedEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            position_id=900,
            used_margin=50_000,
            money_digits=2,
        )
    )

    event = received.only
    assert event.position_id == 900
    assert event.used_margin == 50_000
    assert event.money_digits == 2


async def test_depth_quotes_are_split_into_bids_and_asks(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[DepthEvent] = Recorder()
    routing.subscribe(DepthEvent, received)

    await protocol.emit(
        ProtoOADepthEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            symbol_id=factories.SYMBOL_ID,
            new_quotes=[
                ProtoOADepthQuote(id=1, size=100, bid=108_500),
                ProtoOADepthQuote(id=2, size=200, ask=108_700),
            ],
            deleted_quotes=[7, 8],
        )
    )

    event = received.only
    assert [(q.quote_id, q.price, q.size, q.is_bid) for q in event.new_quotes] == [
        (1, 108_500, 100, True),
        (2, 108_700, 200, False),
    ]
    assert event.deleted_quote_ids == (7, 8)


async def test_a_depth_quote_with_no_price_is_dropped(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    """A quote that is neither a bid nor an ask cannot be placed in the book."""
    received: Recorder[DepthEvent] = Recorder()
    routing.subscribe(DepthEvent, received)

    await protocol.emit(
        ProtoOADepthEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            symbol_id=factories.SYMBOL_ID,
            new_quotes=[ProtoOADepthQuote(id=1, size=100)],
        )
    )

    assert received.only.new_quotes == ()


async def test_token_invalidation_names_the_affected_accounts(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[TokenInvalidatedEvent] = Recorder()
    routing.subscribe(TokenInvalidatedEvent, received)

    await protocol.emit(
        ProtoOAAccountsTokenInvalidatedEvent(
            ctid_trader_account_ids=[factories.ACCOUNT_ID, factories.OTHER_ACCOUNT_ID],
            reason="Token revoked",
        )
    )

    event = received.only
    assert event.account_ids == (factories.ACCOUNT_ID, factories.OTHER_ACCOUNT_ID)
    assert event.reason == "Token revoked"


async def test_a_missing_invalidation_reason_is_still_readable(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[TokenInvalidatedEvent] = Recorder()
    routing.subscribe(TokenInvalidatedEvent, received)

    await protocol.emit(ProtoOAAccountsTokenInvalidatedEvent(ctid_trader_account_ids=[factories.ACCOUNT_ID]))

    assert received.only.reason == "Unknown"


async def test_a_client_disconnect_carries_its_reason(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[ClientDisconnectEvent] = Recorder()
    routing.subscribe(ClientDisconnectEvent, received)

    await protocol.emit(ProtoOAClientDisconnectEvent(reason="Maintenance"))

    assert received.only.reason == "Maintenance"


async def test_an_account_disconnect_names_the_account(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[AccountDisconnectEvent] = Recorder()
    routing.subscribe(AccountDisconnectEvent, received)

    await protocol.emit(ProtoOAAccountDisconnectEvent(ctid_trader_account_id=factories.ACCOUNT_ID))

    assert received.only.account_id == factories.ACCOUNT_ID


async def test_a_symbol_change_lists_the_changed_symbols(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[SymbolChangedEvent] = Recorder()
    routing.subscribe(SymbolChangedEvent, received)

    await protocol.emit(
        ProtoOASymbolChangedEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            symbol_id=[factories.SYMBOL_ID, 271],
        )
    )

    assert received.only.symbol_ids == (factories.SYMBOL_ID, 271)


async def test_a_trailing_stop_change_carries_the_new_level(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[TrailingStopChangedEvent] = Recorder()
    routing.subscribe(TrailingStopChangedEvent, received)

    await protocol.emit(
        ProtoOATrailingSLChangedEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            position_id=900,
            order_id=500,
            stop_price=1.0805,
            utc_last_update_timestamp=TIMESTAMP_MS,
        )
    )

    event = received.only
    assert event.position_id == 900
    assert event.order_id == 500
    assert event.stop_price == Decimal("1.0805")
    assert event.timestamp == TIMESTAMP


async def test_a_margin_call_carries_the_breached_threshold(
    routing: EventEmitter,
    protocol: StubProtocol,
) -> None:
    received: Recorder[MarginCallTriggerEvent] = Recorder()
    routing.subscribe(MarginCallTriggerEvent, received)

    await protocol.emit(
        ProtoOAMarginCallTriggerEvent(
            ctid_trader_account_id=factories.ACCOUNT_ID,
            margin_call=ProtoOAMarginCall(
                margin_call_type=ProtoOANotificationType.MARGIN_LEVEL_THRESHOLD_1,
                margin_level_threshold=50.0,
            ),
        )
    )

    event = received.only
    assert event.margin_call_type == ProtoOANotificationType.MARGIN_LEVEL_THRESHOLD_1
    assert event.margin_level_threshold == Decimal(50)


async def test_an_unrouted_message_reaches_nobody(routing: EventEmitter, protocol: StubProtocol) -> None:
    received: Recorder[SpotEvent] = Recorder()
    routing.subscribe(SpotEvent, received)

    await protocol.emit(ProtoOAClientDisconnectEvent(reason="Maintenance"))

    assert received.count == 0
