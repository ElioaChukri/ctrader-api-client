"""Market data subscriptions and historical requests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

import betterproto
import pytest

from ctrader_api_client._internal.proto import (
    ProtoOAApplicationAuthRes,
    ProtoOAGetTickDataReq,
    ProtoOAGetTickDataRes,
    ProtoOAGetTrendbarsReq,
    ProtoOAGetTrendbarsRes,
    ProtoOAQuoteType,
    ProtoOASubscribeDepthQuotesReq,
    ProtoOASubscribeDepthQuotesRes,
    ProtoOASubscribeLiveTrendbarReq,
    ProtoOASubscribeLiveTrendbarRes,
    ProtoOASubscribeSpotsReq,
    ProtoOASubscribeSpotsRes,
    ProtoOATickData,
    ProtoOATrendbar,
    ProtoOATrendbarPeriod,
    ProtoOAUnsubscribeDepthQuotesReq,
    ProtoOAUnsubscribeDepthQuotesRes,
    ProtoOAUnsubscribeLiveTrendbarReq,
    ProtoOAUnsubscribeLiveTrendbarRes,
    ProtoOAUnsubscribeSpotsReq,
    ProtoOAUnsubscribeSpotsRes,
)
from ctrader_api_client.api import MarketDataAPI
from ctrader_api_client.enums import TrendbarPeriod
from ctrader_api_client.exceptions import APIError

from ...harness import StubProtocol, factories


FROM_TIME = datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
TO_TIME = datetime(2023, 11, 15, 22, 13, 20, tzinfo=UTC)
FROM_MS = 1_700_000_000_000
TO_MS = FROM_MS + 86_400_000
BAR_MINUTES = FROM_MS // 60_000
BAR_TIME = datetime(2023, 11, 14, 22, 13, tzinfo=UTC)


async def test_subscribing_to_spots_asks_for_the_wanted_symbols(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOASubscribeSpotsReq, ProtoOASubscribeSpotsRes())

    await market_data.subscribe_spots(factories.ACCOUNT_ID, [270, 271])

    request = protocol.only_sent(ProtoOASubscribeSpotsReq)
    assert request.ctid_trader_account_id == factories.ACCOUNT_ID
    assert request.symbol_id == [270, 271]
    assert request.subscribe_to_spot_timestamp is True


async def test_unsubscribing_from_spots_names_the_symbols(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOAUnsubscribeSpotsReq, ProtoOAUnsubscribeSpotsRes())

    await market_data.unsubscribe_spots(factories.ACCOUNT_ID, [270])

    assert protocol.only_sent(ProtoOAUnsubscribeSpotsReq).symbol_id == [270]


async def test_subscribing_to_trendbars_names_the_period(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOASubscribeLiveTrendbarReq, ProtoOASubscribeLiveTrendbarRes())

    await market_data.subscribe_trendbars(factories.ACCOUNT_ID, factories.SYMBOL_ID, TrendbarPeriod.H1)

    request = protocol.only_sent(ProtoOASubscribeLiveTrendbarReq)
    assert request.symbol_id == factories.SYMBOL_ID
    assert request.period == ProtoOATrendbarPeriod.H1


async def test_unsubscribing_from_trendbars_names_the_period(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOAUnsubscribeLiveTrendbarReq, ProtoOAUnsubscribeLiveTrendbarRes())

    await market_data.unsubscribe_trendbars(factories.ACCOUNT_ID, factories.SYMBOL_ID, TrendbarPeriod.M5)

    assert protocol.only_sent(ProtoOAUnsubscribeLiveTrendbarReq).period == ProtoOATrendbarPeriod.M5


async def test_subscribing_to_depth_asks_for_the_wanted_symbols(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOASubscribeDepthQuotesReq, ProtoOASubscribeDepthQuotesRes())

    await market_data.subscribe_depth(factories.ACCOUNT_ID, [270, 271])

    assert protocol.only_sent(ProtoOASubscribeDepthQuotesReq).symbol_id == [270, 271]


async def test_unsubscribing_from_depth_names_the_symbols(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOAUnsubscribeDepthQuotesReq, ProtoOAUnsubscribeDepthQuotesRes())

    await market_data.unsubscribe_depth(factories.ACCOUNT_ID, [270])

    assert protocol.only_sent(ProtoOAUnsubscribeDepthQuotesReq).symbol_id == [270]


@pytest.mark.parametrize(
    ("period", "expected"),
    [
        (TrendbarPeriod.M1, ProtoOATrendbarPeriod.M1),
        (TrendbarPeriod.M15, ProtoOATrendbarPeriod.M15),
        (TrendbarPeriod.H1, ProtoOATrendbarPeriod.H1),
        (TrendbarPeriod.D1, ProtoOATrendbarPeriod.D1),
        (TrendbarPeriod.MN1, ProtoOATrendbarPeriod.MN1),
    ],
)
async def test_the_trendbar_request_carries_the_asked_for_period(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
    period: TrendbarPeriod,
    expected: ProtoOATrendbarPeriod,
) -> None:
    protocol.respond(ProtoOAGetTrendbarsReq, ProtoOAGetTrendbarsRes(trendbar=[]))

    await market_data.get_trendbars(factories.ACCOUNT_ID, factories.SYMBOL_ID, period, FROM_TIME, TO_TIME)

    assert protocol.only_sent(ProtoOAGetTrendbarsReq).period == expected


async def test_the_trendbar_request_carries_the_time_range(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOAGetTrendbarsReq, ProtoOAGetTrendbarsRes(trendbar=[]))

    await market_data.get_trendbars(factories.ACCOUNT_ID, factories.SYMBOL_ID, TrendbarPeriod.H1, FROM_TIME, TO_TIME)

    request = protocol.only_sent(ProtoOAGetTrendbarsReq)
    assert request.ctid_trader_account_id == factories.ACCOUNT_ID
    assert request.symbol_id == factories.SYMBOL_ID
    assert request.from_timestamp == FROM_MS
    assert request.to_timestamp == TO_MS


async def test_historical_trendbars_are_returned_as_prices(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(
        ProtoOAGetTrendbarsReq,
        ProtoOAGetTrendbarsRes(
            trendbar=[
                ProtoOATrendbar(
                    volume=1500,
                    period=ProtoOATrendbarPeriod.H1,
                    low=108_500,
                    delta_open=100,
                    delta_high=300,
                    delta_close=200,
                    utc_timestamp_in_minutes=BAR_MINUTES,
                )
            ]
        ),
    )

    bars = await market_data.get_trendbars(
        factories.ACCOUNT_ID, factories.SYMBOL_ID, TrendbarPeriod.H1, FROM_TIME, TO_TIME
    )

    bar = bars[0]
    assert bar.low == Decimal("1.085")
    assert bar.open == Decimal("1.086")
    assert bar.high == Decimal("1.088")
    assert bar.close == Decimal("1.087")
    assert bar.volume == 1500
    assert bar.period is TrendbarPeriod.H1
    assert bar.timestamp == BAR_TIME


async def test_a_historical_bar_may_close_at_its_low(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    """Live bars reject a zero close delta; history legitimately contains them."""
    protocol.respond(
        ProtoOAGetTrendbarsReq,
        ProtoOAGetTrendbarsRes(
            trendbar=[
                ProtoOATrendbar(
                    volume=10,
                    period=ProtoOATrendbarPeriod.M1,
                    low=108_500,
                    delta_open=50,
                    delta_high=50,
                    delta_close=0,
                    utc_timestamp_in_minutes=BAR_MINUTES,
                )
            ]
        ),
    )

    bars = await market_data.get_trendbars(
        factories.ACCOUNT_ID, factories.SYMBOL_ID, TrendbarPeriod.M1, FROM_TIME, TO_TIME
    )

    assert bars[0].close == Decimal("1.085")


async def test_an_empty_trendbar_reply_returns_no_bars(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOAGetTrendbarsReq, ProtoOAGetTrendbarsRes(trendbar=[]))

    bars = await market_data.get_trendbars(
        factories.ACCOUNT_ID, factories.SYMBOL_ID, TrendbarPeriod.H1, FROM_TIME, TO_TIME
    )

    assert bars == []


async def test_tick_data_is_returned_as_absolute_prices(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(
        ProtoOAGetTickDataReq,
        ProtoOAGetTickDataRes(
            tick_data=[
                ProtoOATickData(timestamp=FROM_MS, tick=108_550),
                ProtoOATickData(timestamp=-1000, tick=-50),
            ]
        ),
    )

    ticks = await market_data.get_tick_data(factories.ACCOUNT_ID, factories.SYMBOL_ID, FROM_TIME, TO_TIME)

    assert [t.price for t in ticks] == [Decimal("1.0855"), Decimal("1.085")]
    assert [t.timestamp for t in ticks] == [FROM_TIME, datetime(2023, 11, 14, 22, 13, 19, tzinfo=UTC)]


@pytest.mark.parametrize(
    ("quote_type", "expected"),
    [("BID", ProtoOAQuoteType.BID), ("ASK", ProtoOAQuoteType.ASK), ("bid", ProtoOAQuoteType.BID)],
)
async def test_the_tick_request_carries_the_asked_for_quote_side(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
    quote_type: str,
    expected: ProtoOAQuoteType,
) -> None:
    protocol.respond(ProtoOAGetTickDataReq, ProtoOAGetTickDataRes(tick_data=[]))

    await market_data.get_tick_data(
        factories.ACCOUNT_ID, factories.SYMBOL_ID, FROM_TIME, TO_TIME, quote_type=quote_type
    )

    request = protocol.only_sent(ProtoOAGetTickDataReq)
    assert request.type == expected
    assert request.from_timestamp == FROM_MS
    assert request.to_timestamp == TO_MS


async def test_an_empty_tick_reply_returns_no_ticks(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOAGetTickDataReq, ProtoOAGetTickDataRes(tick_data=[]))

    assert await market_data.get_tick_data(factories.ACCOUNT_ID, factories.SYMBOL_ID, FROM_TIME, TO_TIME) == []


async def test_a_rejected_spot_subscription_reaches_the_caller(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOASubscribeSpotsReq, APIError(error_code="ALREADY_SUBSCRIBED"))

    with pytest.raises(APIError) as exc_info:
        await market_data.subscribe_spots(factories.ACCOUNT_ID, [270])

    assert exc_info.value.error_code == "ALREADY_SUBSCRIBED"


async def _subscribe_spots(api: MarketDataAPI) -> None:
    await api.subscribe_spots(factories.ACCOUNT_ID, [270])


async def _unsubscribe_spots(api: MarketDataAPI) -> None:
    await api.unsubscribe_spots(factories.ACCOUNT_ID, [270])


async def _subscribe_trendbars(api: MarketDataAPI) -> None:
    await api.subscribe_trendbars(factories.ACCOUNT_ID, factories.SYMBOL_ID, TrendbarPeriod.H1)


async def _subscribe_depth(api: MarketDataAPI) -> None:
    await api.subscribe_depth(factories.ACCOUNT_ID, [270])


async def _get_trendbars(api: MarketDataAPI) -> None:
    await api.get_trendbars(factories.ACCOUNT_ID, factories.SYMBOL_ID, TrendbarPeriod.H1, FROM_TIME, TO_TIME)


async def _get_tick_data(api: MarketDataAPI) -> None:
    await api.get_tick_data(factories.ACCOUNT_ID, factories.SYMBOL_ID, FROM_TIME, TO_TIME)


type Call = Callable[[MarketDataAPI], Awaitable[None]]


@pytest.mark.parametrize(
    ("request_type", "call"),
    [
        (ProtoOASubscribeSpotsReq, _subscribe_spots),
        (ProtoOAUnsubscribeSpotsReq, _unsubscribe_spots),
        (ProtoOASubscribeLiveTrendbarReq, _subscribe_trendbars),
        (ProtoOASubscribeDepthQuotesReq, _subscribe_depth),
        (ProtoOAGetTrendbarsReq, _get_trendbars),
        (ProtoOAGetTickDataReq, _get_tick_data),
    ],
)
async def test_an_unexpected_market_data_reply_is_an_error(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
    request_type: type[betterproto.Message],
    call: Call,
) -> None:
    protocol.respond(request_type, ProtoOAApplicationAuthRes())

    with pytest.raises(APIError) as exc_info:
        await call(market_data)

    assert exc_info.value.error_code == "UNEXPECTED_RESPONSE"
