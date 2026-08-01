"""The client as a whole, driven against a real socket."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import betterproto
import pytest

from ctrader_api_client import CTraderClient
from ctrader_api_client._internal.proto import (
    ProtoOAAccountAuthReq,
    ProtoOAAccountDisconnectEvent,
    ProtoOAApplicationAuthReq,
    ProtoOARefreshTokenReq,
)
from ctrader_api_client.auth import AccountCredentials
from ctrader_api_client.events import (
    ReadyEvent,
    ReconnectedEvent,
    SpotEvent,
    TokenRefreshFailedEvent,
)
from ctrader_api_client.exceptions import CTraderConnectionFailedError

from ..harness import FakeServer, ManualClock, Recorder, factories


ALMOST_EXPIRED = 10.0
CHECK_INTERVAL = 60.0


async def authenticate(client: CTraderClient, server: FakeServer) -> AccountCredentials:
    """Bring one account to a live, authorized session."""
    server.respond(ProtoOAApplicationAuthReq, factories.app_auth_res())
    server.respond(ProtoOAAccountAuthReq, factories.account_auth_res())

    credentials = factories.credentials()
    await client.auth.authenticate_app()
    await client.auth.authenticate_account(credentials)
    return credentials


def rejecting(_request: betterproto.Message) -> betterproto.Message:
    """Reject whatever is asked."""
    return factories.error_res(error_code="ACCOUNT_NOT_AUTHORIZED")


# -----------------------------------------------------------------------------
# Lifecycle
# -----------------------------------------------------------------------------


async def test_connecting_opens_a_link_to_the_server(
    make_client: Callable[..., CTraderClient],
    server: FakeServer,
) -> None:
    client = make_client()

    await client.connect()

    assert client.is_connected is True
    assert server.connection_count == 1


async def test_connecting_an_already_connected_client_changes_nothing(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    await client.connect()

    assert server.connection_count == 1
    assert client.is_connected is True


async def test_closing_drops_the_link(client: CTraderClient, server: FakeServer) -> None:
    await client.close()
    await server.wait_for_disconnect()

    assert client.is_connected is False


async def test_closing_an_already_closed_client_is_harmless(client: CTraderClient) -> None:
    await client.close()
    await client.close()

    assert client.is_connected is False


async def test_the_context_manager_connects_and_closes(
    make_client: Callable[..., CTraderClient],
    server: FakeServer,
) -> None:
    client = make_client()

    async with client as connected:
        assert connected.is_connected is True
        assert server.connection_count == 1

    assert client.is_connected is False


async def test_connecting_to_a_server_that_is_not_there_fails(
    make_client: Callable[..., CTraderClient],
) -> None:
    # Nothing listens on port 1, so a loopback connect is refused immediately.
    client = make_client(port=1)

    with pytest.raises(CTraderConnectionFailedError):
        await client.connect()

    assert client.is_connected is False


# -----------------------------------------------------------------------------
# Event delivery
# -----------------------------------------------------------------------------


async def test_a_pushed_price_reaches_a_registered_handler(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    prices: Recorder[SpotEvent] = Recorder()
    client.register_handler(SpotEvent, prices, symbol_id=factories.SYMBOL_ID)

    await server.push(factories.spot_event(bid=108_500, ask=108_700))
    await prices.wait_for(1)

    assert prices.only.symbol_id == factories.SYMBOL_ID
    assert prices.only.bid == Decimal("1.085")
    assert prices.only.ask == Decimal("1.087")


async def test_a_handler_filtered_by_symbol_ignores_other_symbols(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    wanted: Recorder[SpotEvent] = Recorder()
    everything: Recorder[SpotEvent] = Recorder()
    client.register_handler(SpotEvent, wanted, symbol_id=factories.SYMBOL_ID)
    client.register_handler(SpotEvent, everything)

    await server.push(factories.spot_event(symbol_id=999))
    await server.push(factories.spot_event(symbol_id=factories.SYMBOL_ID))
    await everything.wait_for(2)

    assert [event.symbol_id for event in wanted.items] == [factories.SYMBOL_ID]


async def test_a_handler_registered_by_decorator_receives_events(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    prices: Recorder[SpotEvent] = Recorder()

    @client.on(SpotEvent, symbol_id=factories.SYMBOL_ID)
    async def on_price(event: SpotEvent) -> None:
        await prices(event)

    await server.push(factories.spot_event())
    await prices.wait_for(1)

    assert prices.only.symbol_id == factories.SYMBOL_ID


async def test_an_unregistered_handler_stops_receiving_events(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    prices: Recorder[SpotEvent] = Recorder()
    remaining: Recorder[SpotEvent] = Recorder()
    client.register_handler(SpotEvent, prices)
    client.register_handler(SpotEvent, remaining)

    assert client.off(SpotEvent, prices) is True

    await server.push(factories.spot_event())
    await remaining.wait_for(1)

    assert prices.count == 0


async def test_unregistering_a_handler_that_was_never_registered_reports_so(
    client: CTraderClient,
) -> None:
    prices: Recorder[SpotEvent] = Recorder()

    assert client.off(SpotEvent, prices) is False


async def test_an_authenticated_account_is_announced_as_ready(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    ready: Recorder[ReadyEvent] = Recorder()
    client.register_handler(ReadyEvent, ready)

    await authenticate(client, server)
    await ready.wait_for(1)

    assert ready.only.account_id == factories.ACCOUNT_ID
    assert ready.only.is_reconnect is False


# -----------------------------------------------------------------------------
# Reconnection
# -----------------------------------------------------------------------------


async def test_a_reconnect_restores_the_application_and_its_accounts(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    await authenticate(client, server)
    reconnects: Recorder[ReconnectedEvent] = Recorder()
    client.register_handler(ReconnectedEvent, reconnects)

    await server.drop_connection()
    await reconnects.wait_for(1)

    assert reconnects.only.app_auth_restored is True
    assert reconnects.only.restored_accounts == (factories.ACCOUNT_ID,)
    assert reconnects.only.failed_accounts == ()
    assert client.is_account_authorized(factories.ACCOUNT_ID) is True


async def test_a_restored_account_is_announced_as_ready_again(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    """Subscriptions are dropped with the connection, so the account must be re-announced."""
    await authenticate(client, server)
    ready: Recorder[ReadyEvent] = Recorder()
    client.register_handler(ReadyEvent, ready)

    await server.drop_connection()
    await ready.wait_for(1)

    assert ready.only.account_id == factories.ACCOUNT_ID
    assert ready.only.is_reconnect is True


async def test_a_reconnect_reports_accounts_it_could_not_restore(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    await authenticate(client, server)
    server.on(ProtoOAAccountAuthReq, rejecting)
    reconnects: Recorder[ReconnectedEvent] = Recorder()
    client.register_handler(ReconnectedEvent, reconnects)

    await server.drop_connection()
    await reconnects.wait_for(1)

    assert reconnects.only.app_auth_restored is True
    assert reconnects.only.restored_accounts == ()
    assert [account_id for account_id, _reason in reconnects.only.failed_accounts] == [factories.ACCOUNT_ID]


async def test_a_reconnect_that_cannot_re_authenticate_the_app_says_so(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    """Without app auth nothing else can be restored, so no account is claimed either."""
    await authenticate(client, server)
    server.on(ProtoOAApplicationAuthReq, rejecting)
    reconnects: Recorder[ReconnectedEvent] = Recorder()
    client.register_handler(ReconnectedEvent, reconnects)

    await server.drop_connection()
    await reconnects.wait_for(1)

    assert reconnects.only.app_auth_restored is False
    assert reconnects.only.restored_accounts == ()
    assert reconnects.only.failed_accounts == ()


async def test_an_account_a_reconnect_could_not_restore_is_not_authorized(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    """The session lives on the server, so it dies with the link that carried it.

    Reporting the account as authorized once the link is back but the session
    is not would let callers send account requests that cannot be answered.
    """
    await authenticate(client, server)
    server.on(ProtoOAAccountAuthReq, rejecting)
    reconnects: Recorder[ReconnectedEvent] = Recorder()
    client.register_handler(ReconnectedEvent, reconnects)

    await server.drop_connection()
    await reconnects.wait_for(1)

    assert client.is_account_authorized(factories.ACCOUNT_ID) is False


# -----------------------------------------------------------------------------
# Account recovery
# -----------------------------------------------------------------------------


async def test_an_account_the_server_drops_is_re_authenticated(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    await authenticate(client, server)
    ready: Recorder[ReadyEvent] = Recorder()
    client.register_handler(ReadyEvent, ready)

    await server.push(ProtoOAAccountDisconnectEvent(ctid_trader_account_id=factories.ACCOUNT_ID))
    await ready.wait_for(1)

    assert ready.only.is_reconnect is True
    assert client.is_account_authorized(factories.ACCOUNT_ID) is True


async def test_a_dropped_account_stays_unauthorized_until_recovery_succeeds(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    await authenticate(client, server)
    server.on(ProtoOAAccountAuthReq, rejecting)

    await server.push(ProtoOAAccountDisconnectEvent(ctid_trader_account_id=factories.ACCOUNT_ID))
    await server.wait_for_request(ProtoOAAccountAuthReq, count=2)

    assert client.is_account_authorized(factories.ACCOUNT_ID) is False
    assert client.is_connected is True


# -----------------------------------------------------------------------------
# Token refresh
# -----------------------------------------------------------------------------


async def test_a_token_refresh_that_fails_is_reported_as_an_event(
    make_client: Callable[..., CTraderClient],
    server: FakeServer,
    clock: ManualClock,
) -> None:
    """The account keeps running on its old token, so the failure needs its own signal."""
    client = make_client(reconnect_attempts=0)
    await client.connect()
    server.respond(ProtoOAApplicationAuthReq, factories.app_auth_res())
    server.respond(ProtoOAAccountAuthReq, factories.account_auth_res())
    await client.auth.authenticate_app()
    await client.auth.authenticate_account(factories.credentials(expires_in=ALMOST_EXPIRED))

    failures: Recorder[TokenRefreshFailedEvent] = Recorder()
    client.register_handler(TokenRefreshFailedEvent, failures)

    await server.drop_connection()
    await server.wait_for_disconnect()
    await clock.wait_for_sleepers(1)
    await clock.advance(CHECK_INTERVAL)
    await failures.wait_for(1)

    assert failures.only.account_id == factories.ACCOUNT_ID
    assert server.requests_of(ProtoOARefreshTokenReq) == []


async def test_no_refresh_is_attempted_while_tokens_are_fresh(
    client: CTraderClient,
    server: FakeServer,
    clock: ManualClock,
) -> None:
    await authenticate(client, server)

    await clock.wait_for_sleepers(2)
    await clock.advance(CHECK_INTERVAL)

    assert server.requests_of(ProtoOARefreshTokenReq) == []
