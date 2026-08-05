"""Re-applying standing market data subscriptions to a fresh session."""

from __future__ import annotations

from ctrader_api_client._internal.proto import (
    ProtoOASubscribeDepthQuotesReq,
    ProtoOASubscribeDepthQuotesRes,
    ProtoOASubscribeLiveTrendbarReq,
    ProtoOASubscribeLiveTrendbarRes,
    ProtoOASubscribeSpotsReq,
    ProtoOASubscribeSpotsRes,
    ProtoOAUnsubscribeSpotsReq,
    ProtoOAUnsubscribeSpotsRes,
)
from ctrader_api_client.api import MarketDataAPI
from ctrader_api_client.enums import TrendbarPeriod
from ctrader_api_client.events import SubscriptionRestoreFailedEvent
from ctrader_api_client.exceptions import APIError

from ...harness import RecordingPublisher, StubProtocol, factories


OTHER_ACCOUNT_ID = factories.ACCOUNT_ID + 1


def allow_subscriptions(protocol: StubProtocol) -> None:
    protocol.respond(ProtoOASubscribeSpotsReq, ProtoOASubscribeSpotsRes())
    protocol.respond(ProtoOASubscribeLiveTrendbarReq, ProtoOASubscribeLiveTrendbarRes())
    protocol.respond(ProtoOASubscribeDepthQuotesReq, ProtoOASubscribeDepthQuotesRes())
    protocol.respond(ProtoOAUnsubscribeSpotsReq, ProtoOAUnsubscribeSpotsRes())


async def test_a_standing_spot_subscription_is_re_applied(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    allow_subscriptions(protocol)
    await market_data.subscribe_spots(factories.ACCOUNT_ID, [270, 271])

    await market_data.restore(factories.ACCOUNT_ID)

    assert [request.symbol_id for request in protocol.sent_of(ProtoOASubscribeSpotsReq)] == [[270, 271], [270, 271]]


async def test_a_forgotten_account_is_not_re_applied(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    """Forgetting drops the intent, so a later session starts clean."""
    allow_subscriptions(protocol)
    await market_data.subscribe_spots(factories.ACCOUNT_ID, [270])
    market_data.forget(factories.ACCOUNT_ID)
    protocol.clear_sent()

    await market_data.restore(factories.ACCOUNT_ID)

    assert protocol.sent == []


async def test_forgetting_one_account_leaves_the_others_standing(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    allow_subscriptions(protocol)
    await market_data.subscribe_spots(factories.ACCOUNT_ID, [270])
    await market_data.subscribe_spots(OTHER_ACCOUNT_ID, [271])
    market_data.forget(factories.ACCOUNT_ID)
    protocol.clear_sent()

    await market_data.restore(OTHER_ACCOUNT_ID)

    assert protocol.sent_of(ProtoOASubscribeSpotsReq)[-1].symbol_id == [271]


async def test_forgetting_an_unknown_account_is_harmless(market_data: MarketDataAPI) -> None:
    market_data.forget(OTHER_ACCOUNT_ID)


async def test_an_unsubscribed_symbol_is_not_re_applied(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    """Unsubscribing withdraws the intent, not just the current subscription."""
    allow_subscriptions(protocol)
    await market_data.subscribe_spots(factories.ACCOUNT_ID, [270, 271])
    await market_data.unsubscribe_spots(factories.ACCOUNT_ID, [271])

    await market_data.restore(factories.ACCOUNT_ID)

    assert protocol.sent_of(ProtoOASubscribeSpotsReq)[-1].symbol_id == [270]


async def test_spots_are_re_applied_before_the_trendbars_that_need_them(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    """The server rejects a trendbar subscription unless spots are already live."""
    allow_subscriptions(protocol)
    await market_data.subscribe_spots(factories.ACCOUNT_ID, [270])
    await market_data.subscribe_trendbars(factories.ACCOUNT_ID, 270, TrendbarPeriod.H1)
    protocol.clear_sent()

    await market_data.restore(factories.ACCOUNT_ID)

    assert [type(request) for request in protocol.sent] == [
        ProtoOASubscribeSpotsReq,
        ProtoOASubscribeLiveTrendbarReq,
    ]


async def test_depth_is_re_applied(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    allow_subscriptions(protocol)
    await market_data.subscribe_depth(factories.ACCOUNT_ID, [270])
    protocol.clear_sent()

    await market_data.restore(factories.ACCOUNT_ID)

    assert protocol.only_sent(ProtoOASubscribeDepthQuotesReq).symbol_id == [270]


async def test_only_the_named_account_is_re_applied(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    allow_subscriptions(protocol)
    await market_data.subscribe_spots(factories.ACCOUNT_ID, [270])
    await market_data.subscribe_spots(OTHER_ACCOUNT_ID, [271])
    protocol.clear_sent()

    await market_data.restore(factories.ACCOUNT_ID)

    assert protocol.only_sent(ProtoOASubscribeSpotsReq).ctid_trader_account_id == factories.ACCOUNT_ID


async def test_an_account_that_asked_for_nothing_sends_nothing(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    await market_data.restore(factories.ACCOUNT_ID)

    assert protocol.sent == []


async def test_a_failed_restore_is_reported(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
    publisher: RecordingPublisher,
) -> None:
    """Silently missing prices is worse than a loud failure."""
    allow_subscriptions(protocol)
    await market_data.subscribe_spots(factories.ACCOUNT_ID, [270])
    protocol.respond(ProtoOASubscribeSpotsReq, APIError(error_code="NOT_SUBSCRIBABLE"))

    await market_data.restore(factories.ACCOUNT_ID)

    reported = publisher.only_of(SubscriptionRestoreFailedEvent)
    assert reported.account_id == factories.ACCOUNT_ID
    assert isinstance(reported.error, APIError)


async def test_a_failed_restore_does_not_raise_at_the_caller(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    """Authentication must not fail because the feed could not be reinstated."""
    allow_subscriptions(protocol)
    await market_data.subscribe_spots(factories.ACCOUNT_ID, [270])
    protocol.respond(ProtoOASubscribeSpotsReq, APIError(error_code="NOT_SUBSCRIBABLE"))

    await market_data.restore(factories.ACCOUNT_ID)


async def test_a_failure_stops_the_rest_of_the_restore(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    """Trendbars would only fail again without their spots."""
    allow_subscriptions(protocol)
    await market_data.subscribe_spots(factories.ACCOUNT_ID, [270])
    await market_data.subscribe_trendbars(factories.ACCOUNT_ID, 270, TrendbarPeriod.H1)
    protocol.respond(ProtoOASubscribeSpotsReq, APIError(error_code="NOT_SUBSCRIBABLE"))
    protocol.clear_sent()

    await market_data.restore(factories.ACCOUNT_ID)

    assert protocol.sent_of(ProtoOASubscribeLiveTrendbarReq) == []


async def test_a_failed_restore_is_tried_again_next_time(
    market_data: MarketDataAPI,
    protocol: StubProtocol,
) -> None:
    """The intent survives the failure, so the next reconnection picks it up."""
    allow_subscriptions(protocol)
    await market_data.subscribe_spots(factories.ACCOUNT_ID, [270])
    protocol.respond(ProtoOASubscribeSpotsReq, APIError(error_code="NOT_SUBSCRIBABLE"))
    await market_data.restore(factories.ACCOUNT_ID)

    protocol.respond(ProtoOASubscribeSpotsReq, ProtoOASubscribeSpotsRes())
    protocol.clear_sent()
    await market_data.restore(factories.ACCOUNT_ID)

    assert protocol.only_sent(ProtoOASubscribeSpotsReq).symbol_id == [270]
