"""The client as a whole, driven against a real socket."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

import betterproto
import pytest

from ctrader_api_client import CTraderClient
from ctrader_api_client._internal.proto import (
    ProtoOAAccountAuthReq,
    ProtoOAAccountDisconnectEvent,
    ProtoOAApplicationAuthReq,
    ProtoOARefreshTokenReq,
    ProtoOATraderReq,
)
from ctrader_api_client.auth import AccountCredentials, ReauthPolicy
from ctrader_api_client.events import (
    AccountDisconnectEvent,
    ReadyEvent,
    ReconnectedEvent,
    SpotEvent,
    TokenRefreshFailedEvent,
)
from ctrader_api_client.exceptions import (
    ApplicationAuthError,
    CTraderConnectionClosedError,
    CTraderConnectionFailedError,
)

from ..harness import FakeServer, ManualClock, Recorder, factories


ALMOST_EXPIRED = 10.0
CHECK_INTERVAL = 60.0
RETRY_WAIT = 1.0

# The heartbeat loop and the token-refresh loop, both parked on the clock once a
# client is up. Captured rather than assumed where a test needs to tell a new
# sleeper apart from these.
SLEEPERS_WHEN_CONNECTED = 2


async def authenticate(client: CTraderClient, server: FakeServer) -> AccountCredentials:
    """Bring one account to a live, authorized session."""
    server.respond(ProtoOAAccountAuthReq, factories.account_auth_res())

    credentials = factories.credentials()
    await client.auth.authenticate_trader(credentials)
    return credentials


def rejecting(_request: betterproto.Message) -> betterproto.Message:
    """Reject whatever is asked."""
    return factories.error_res(error_code="ACCOUNT_NOT_AUTHORIZED")


def cannot_route_once() -> Callable[[betterproto.Message], betterproto.Message]:
    """Refuse the first request the way a gateway refuses to route one, then relent.

    `CANT_ROUTE_REQUEST` is transient and server-side: the same request a moment
    later is routed normally.
    """
    refusals = [factories.error_res(error_code="CANT_ROUTE_REQUEST", description="Cannot route request")]

    def respond(_request: betterproto.Message) -> betterproto.Message:
        return refusals.pop() if refusals else factories.app_auth_res()

    return respond


def already_logged_in(_request: betterproto.Message) -> betterproto.Message:
    """Refuse the way the server refuses an account whose session is still live."""
    return factories.error_res(
        error_code="ALREADY_LOGGED_IN",
        description="Trading account is already authorized in this channel",
    )


# -----------------------------------------------------------------------------
# Lifecycle
# -----------------------------------------------------------------------------


async def test_connecting_opens_a_link_to_the_server(
    make_client: Callable[..., CTraderClient],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
    server: FakeServer,
) -> None:
    client = await connected(make_client())

    assert client.is_connected is True
    assert server.connection_count == 1


async def test_connecting_authenticates_the_application(
    make_client: Callable[..., CTraderClient],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
    server: FakeServer,
) -> None:
    """Nothing else can be asked of the server until the app is authenticated."""
    client = await connected(make_client())

    assert client.auth.is_app_authenticated is True
    assert len(server.requests_of(ProtoOAApplicationAuthReq)) == 1


async def test_a_rejected_application_stops_the_client_coming_up(
    make_client: Callable[..., CTraderClient],
    server: FakeServer,
) -> None:
    """A client that cannot authenticate is of no use, so it does not open."""
    server.respond(
        ProtoOAApplicationAuthReq,
        factories.error_res(error_code="CH_CLIENT_AUTH_FAILURE", description="bad credentials"),
    )
    client = make_client()

    with pytest.raises(ApplicationAuthError):
        async with client:
            pass

    assert client.is_connected is False


async def test_leaving_the_block_drops_the_link(
    make_client: Callable[..., CTraderClient],
    server: FakeServer,
) -> None:
    client = make_client()

    async with client:
        pass
    await server.wait_for_disconnect()

    assert client.is_connected is False


async def test_reconnecting_a_client_that_is_still_up_is_refused(
    client: CTraderClient,
) -> None:
    """Entering twice would start a second set of loops the first would outlive."""
    with pytest.raises(RuntimeError):
        async with client:
            pass

    assert client.is_connected is True


async def test_sending_after_closing_is_rejected(
    make_client: Callable[..., CTraderClient],
) -> None:
    """A closed connection must fail fast rather than hang or silently drop the call."""
    client = make_client()
    async with client:
        pass

    with pytest.raises(CTraderConnectionClosedError):
        await client.protocol.send_request(ProtoOAApplicationAuthReq())

    with pytest.raises(CTraderConnectionClosedError):
        await client.protocol.send_event(ProtoOAApplicationAuthReq())


async def test_the_context_manager_connects_and_closes(
    make_client: Callable[..., CTraderClient],
    server: FakeServer,
) -> None:
    client = make_client()

    async with client as connecting:
        assert connecting.is_connected is True
        assert server.connection_count == 1

    assert client.is_connected is False


async def test_connecting_to_a_server_that_is_not_there_fails(
    make_client: Callable[..., CTraderClient],
) -> None:
    # Nothing listens on port 1, so a loopback connect is refused immediately.
    client = make_client(port=1)

    with pytest.raises(CTraderConnectionFailedError):
        async with client:
            pass

    assert client.is_connected is False


async def test_an_exception_from_the_block_reaches_the_caller_as_itself(
    make_client: Callable[..., CTraderClient],
) -> None:
    """The background task group must not turn the caller's own error into a group.

    The block's exception is carried out through the task group holding the
    background tasks, and a task group reports even a single failure as an
    ExceptionGroup. Callers write `except ValueError`, not `except*`.
    """
    client = make_client()

    with pytest.raises(ValueError, match="from the block"):
        async with client:
            raise ValueError("from the block")

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


async def test_a_reconnect_keeps_retrying_application_authentication(
    make_client: Callable[..., CTraderClient],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
    server: FakeServer,
) -> None:
    """A transient refusal must not cost the client the rest of its session.

    Regression guard: application re-authentication used to be attempted exactly
    once per reconnect. A single transient refusal left the link up but
    unauthenticated, with no path back — every later request timed out, and
    because the link itself was healthy nothing ever reconnected again.
    """
    client = await connected(make_client(reauth_policy=ReauthPolicy(min_wait=0.0, max_wait=0.0)))
    await authenticate(client, server)
    ready: Recorder[ReadyEvent] = Recorder()
    client.register_handler(ReadyEvent, ready)
    server.on(ProtoOAApplicationAuthReq, cannot_route_once())

    await server.drop_connection()
    await ready.wait_for(1)

    assert client.is_account_authorized(factories.ACCOUNT_ID) is True
    assert ready.only.account_id == factories.ACCOUNT_ID
    assert ready.only.is_reconnect is True


async def test_retrying_application_authentication_waits_out_its_backoff(
    make_client: Callable[..., CTraderClient],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
    server: FakeServer,
    clock: ManualClock,
) -> None:
    """Retrying is paced by the policy, not spun as fast as the server refuses.

    A server that keeps refusing is usually one under strain; hammering it as
    fast as the loop can go would pin a core and make that worse.
    """
    client = await connected(make_client(reauth_policy=ReauthPolicy(min_wait=RETRY_WAIT, max_wait=RETRY_WAIT)))
    await authenticate(client, server)
    await clock.wait_for_sleepers(SLEEPERS_WHEN_CONNECTED)
    parked = clock.sleeper_count
    server.on(ProtoOAApplicationAuthReq, rejecting)

    await server.drop_connection()
    # The attempt the reconnection itself makes, which the server refuses.
    await server.wait_for_request(ProtoOAApplicationAuthReq, 2)
    # Recovery has taken it over and is parked on the backoff before retrying.
    await clock.wait_for_sleepers(parked + 1)

    assert len(server.requests_of(ProtoOAApplicationAuthReq)) == 2

    await clock.advance(RETRY_WAIT)
    await server.wait_for_request(ProtoOAApplicationAuthReq, 3)

    assert len(server.requests_of(ProtoOAApplicationAuthReq)) == 3


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
    # The server stands behind the report: it will not answer for the account.
    server.on(ProtoOATraderReq, rejecting)

    await server.push(ProtoOAAccountDisconnectEvent(ctid_trader_account_id=factories.ACCOUNT_ID))
    await ready.wait_for(1)

    assert ready.only.is_reconnect is True
    assert client.is_account_authorized(factories.ACCOUNT_ID) is True


async def test_a_dropped_account_stays_unauthorized_until_recovery_succeeds(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    await authenticate(client, server)
    dropped: Recorder[AccountDisconnectEvent] = Recorder()
    client.register_handler(AccountDisconnectEvent, dropped)
    server.on(ProtoOATraderReq, rejecting)
    server.on(ProtoOAAccountAuthReq, rejecting)

    await server.push(ProtoOAAccountDisconnectEvent(ctid_trader_account_id=factories.ACCOUNT_ID))
    # The drop is published once the server has confirmed it, which is also when
    # the account stops counting as authorized.
    await dropped.wait_for(1)

    assert client.is_account_authorized(factories.ACCOUNT_ID) is False
    assert client.is_connected is True


async def test_a_disconnect_the_server_does_not_stand_behind_is_not_published(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    """A token rotation makes the server report a disconnect it did not perform."""
    await authenticate(client, server)
    dropped: Recorder[AccountDisconnectEvent] = Recorder()
    ready: Recorder[ReadyEvent] = Recorder()
    client.register_handler(AccountDisconnectEvent, dropped)
    client.register_handler(ReadyEvent, ready)
    server.respond(ProtoOATraderReq, factories.trader_res())

    await server.push(ProtoOAAccountDisconnectEvent(ctid_trader_account_id=factories.ACCOUNT_ID))
    await server.wait_for_request(ProtoOATraderReq)

    assert dropped.count == 0
    assert ready.count == 0
    assert client.is_account_authorized(factories.ACCOUNT_ID) is True
    # The account was never re-authorized, only asked after.
    assert len(server.requests_of(ProtoOAAccountAuthReq)) == 1


# -----------------------------------------------------------------------------
# Token refresh
# -----------------------------------------------------------------------------


async def test_a_token_refresh_that_fails_is_reported_as_an_event(
    make_client: Callable[..., CTraderClient],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
    server: FakeServer,
    clock: ManualClock,
) -> None:
    """The account keeps running on its old token, so the failure needs its own signal."""
    client = await connected(make_client(reconnect_attempts=0))
    server.respond(ProtoOAAccountAuthReq, factories.account_auth_res())
    await client.auth.authenticate_trader(factories.credentials(expires_in=ALMOST_EXPIRED))

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
