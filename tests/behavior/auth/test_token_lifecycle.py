"""Keeping accounts usable: token refresh and recovery after a server disconnect."""

from __future__ import annotations

from collections.abc import Callable

import anyio
import betterproto
import pytest

from ctrader_api_client._internal.proto import (
    ProtoOAAccountAuthReq,
    ProtoOARefreshTokenReq,
    ProtoOATraderReq,
)
from ctrader_api_client.auth import AuthManager, ReauthPolicy, SessionRecovery, SessionStore
from ctrader_api_client.enums import AuthTrigger
from ctrader_api_client.events import AccountDisconnectEvent, ReadyEvent, TokenRefreshFailedEvent
from ctrader_api_client.exceptions import APIError, CTraderConnectionTimeoutError, TokenExpiredError

from ...harness import ManualClock, RecordingPublisher, RecordingStore, StubProtocol, factories
from .conftest import Monitors


CHECK_INTERVAL = 60.0

# The refresh loop is the only clock sleeper the monitors park in until a
# recovery backoff is armed.
SLEEPERS_WHEN_STARTED = 1

ALMOST_EXPIRED = 10.0
PLENTY_OF_TIME = 86_400.0


async def start_with_account(
    auth: AuthManager,
    protocol: StubProtocol,
    clock: ManualClock,
    expires_in: float,
) -> None:
    """Authenticate one account and let the background loops settle."""
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())
    await auth.authenticate_trader(factories.credentials(expires_in=expires_in))
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED)


async def test_a_token_near_expiry_is_refreshed(
    auth: AuthManager,
    make_monitors: Callable[..., Monitors],
    protocol: StubProtocol,
    clock: ManualClock,
) -> None:
    store = RecordingStore()
    make_monitors(token_store=store, check_interval=CHECK_INTERVAL)
    protocol.respond(ProtoOARefreshTokenReq, factories.refresh_token_res())
    await start_with_account(auth, protocol, clock, expires_in=ALMOST_EXPIRED)

    await clock.advance(CHECK_INTERVAL)
    await store.wait_for(1)

    stored = auth.get_credentials(factories.ACCOUNT_ID)
    assert stored is not None
    assert stored.access_token == "new-access-token"
    assert stored.refresh_token == "new-refresh-token"


@pytest.mark.usefixtures("monitors")
async def test_the_refresh_request_carries_the_current_refresh_token(
    auth: AuthManager,
    protocol: StubProtocol,
    clock: ManualClock,
) -> None:
    protocol.respond(ProtoOARefreshTokenReq, factories.refresh_token_res())
    await start_with_account(auth, protocol, clock, expires_in=ALMOST_EXPIRED)

    await clock.advance(CHECK_INTERVAL)
    await protocol.wait_for_sent(ProtoOARefreshTokenReq)

    assert protocol.only_sent(ProtoOARefreshTokenReq).refresh_token == factories.REFRESH_TOKEN


@pytest.mark.usefixtures("monitors")
async def test_a_refreshed_account_is_re_authenticated_with_the_new_token(
    auth: AuthManager,
    protocol: StubProtocol,
    clock: ManualClock,
) -> None:
    """The server session is bound to the old token, so it has to be renewed too."""
    protocol.respond(ProtoOARefreshTokenReq, factories.refresh_token_res())
    await start_with_account(auth, protocol, clock, expires_in=ALMOST_EXPIRED)

    await clock.advance(CHECK_INTERVAL)
    await protocol.wait_for_sent(ProtoOAAccountAuthReq, count=2)

    assert protocol.sent_of(ProtoOAAccountAuthReq)[-1].access_token == "new-access-token"
    assert auth.is_account_authorized(factories.ACCOUNT_ID)


@pytest.mark.usefixtures("monitors")
async def test_a_token_with_time_left_is_not_refreshed(
    auth: AuthManager,
    protocol: StubProtocol,
    clock: ManualClock,
) -> None:
    protocol.respond(ProtoOARefreshTokenReq, factories.refresh_token_res())
    await start_with_account(auth, protocol, clock, expires_in=PLENTY_OF_TIME)

    await clock.advance(CHECK_INTERVAL)
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED)

    assert protocol.sent_of(ProtoOARefreshTokenReq) == []


async def test_a_refresh_that_fails_once_still_succeeds(
    auth: AuthManager,
    make_monitors: Callable[..., Monitors],
    protocol: StubProtocol,
    clock: ManualClock,
) -> None:
    store = RecordingStore()
    make_monitors(token_store=store, check_interval=CHECK_INTERVAL)
    protocol.respond_in_sequence(
        ProtoOARefreshTokenReq,
        [APIError(error_code="TEMPORARY"), factories.refresh_token_res()],
    )
    await start_with_account(auth, protocol, clock, expires_in=ALMOST_EXPIRED)

    await clock.advance(CHECK_INTERVAL)
    await store.wait_for(1)

    stored = auth.get_credentials(factories.ACCOUNT_ID)
    assert stored is not None
    assert stored.access_token == "new-access-token"


@pytest.mark.usefixtures("monitors")
async def test_a_refresh_that_keeps_failing_leaves_the_old_credentials_in_place(
    auth: AuthManager,
    protocol: StubProtocol,
    clock: ManualClock,
) -> None:
    """Half-updated credentials would be worse than stale ones."""
    protocol.respond(ProtoOARefreshTokenReq, APIError(error_code="CH_ACCESS_TOKEN_INVALID"))
    await start_with_account(auth, protocol, clock, expires_in=ALMOST_EXPIRED)

    await clock.advance(CHECK_INTERVAL)
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED)

    stored = auth.get_credentials(factories.ACCOUNT_ID)
    assert stored is not None
    assert stored.access_token == factories.ACCESS_TOKEN


@pytest.mark.usefixtures("monitors")
async def test_a_failed_refresh_is_reported(
    auth: AuthManager,
    protocol: StubProtocol,
    clock: ManualClock,
    publisher: RecordingPublisher,
) -> None:
    protocol.respond(ProtoOARefreshTokenReq, APIError(error_code="TEMPORARY"))
    await start_with_account(auth, protocol, clock, expires_in=ALMOST_EXPIRED)

    await clock.advance(CHECK_INTERVAL)
    await publisher.wait_for_type(TokenRefreshFailedEvent)

    failure = publisher.only_of(TokenRefreshFailedEvent)
    assert failure.account_id == factories.ACCOUNT_ID
    assert isinstance(failure.error.cause, APIError)


@pytest.mark.usefixtures("monitors")
async def test_a_dead_refresh_token_is_reported_without_being_retried(
    auth: AuthManager,
    protocol: StubProtocol,
    clock: ManualClock,
    publisher: RecordingPublisher,
) -> None:
    """Retrying a token the server has already revoked only wastes the refresh window."""
    protocol.respond(ProtoOARefreshTokenReq, APIError(error_code="OA_AUTH_TOKEN_EXPIRED"))
    await start_with_account(auth, protocol, clock, expires_in=ALMOST_EXPIRED)

    await clock.advance(CHECK_INTERVAL)
    await publisher.wait_for_type(TokenRefreshFailedEvent)

    assert isinstance(publisher.only_of(TokenRefreshFailedEvent).error.cause, TokenExpiredError)
    assert len(protocol.sent_of(ProtoOARefreshTokenReq)) == 1


async def test_refreshing_resumes_after_a_failed_attempt(
    auth: AuthManager,
    make_monitors: Callable[..., Monitors],
    protocol: StubProtocol,
    clock: ManualClock,
) -> None:
    """A refresh outage must not silently retire the refresh monitor."""
    store = RecordingStore()
    make_monitors(token_store=store, check_interval=CHECK_INTERVAL)
    protocol.respond_in_sequence(
        ProtoOARefreshTokenReq,
        [
            APIError(error_code="TEMPORARY"),
            APIError(error_code="TEMPORARY"),
            APIError(error_code="TEMPORARY"),
            factories.refresh_token_res(),
        ],
    )
    await start_with_account(auth, protocol, clock, expires_in=ALMOST_EXPIRED)

    await clock.advance(CHECK_INTERVAL)
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED)
    await clock.advance(CHECK_INTERVAL)
    await store.wait_for(1)

    stored = auth.get_credentials(factories.ACCOUNT_ID)
    assert stored is not None
    assert stored.access_token == "new-access-token"


@pytest.mark.usefixtures("monitors")
async def test_a_failing_refresh_report_does_not_retire_the_monitor(
    auth: AuthManager,
    protocol: StubProtocol,
    clock: ManualClock,
    publisher: RecordingPublisher,
) -> None:
    protocol.respond(ProtoOARefreshTokenReq, APIError(error_code="TEMPORARY"))
    await start_with_account(auth, protocol, clock, expires_in=ALMOST_EXPIRED)

    await clock.advance(CHECK_INTERVAL)
    await publisher.wait_for_type(TokenRefreshFailedEvent)
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED)
    await clock.advance(CHECK_INTERVAL)
    await publisher.wait_for_type(TokenRefreshFailedEvent, count=2)

    assert len(publisher.of(TokenRefreshFailedEvent)) == 2


async def test_a_refresh_does_not_announce_the_account_as_ready(
    auth: AuthManager,
    make_monitors: Callable[..., Monitors],
    protocol: StubProtocol,
    clock: ManualClock,
    publisher: RecordingPublisher,
) -> None:
    """The session is renewed in place, so there are no subscriptions to reapply."""
    store = RecordingStore()
    make_monitors(token_store=store, check_interval=CHECK_INTERVAL)
    protocol.respond(ProtoOARefreshTokenReq, factories.refresh_token_res())
    await start_with_account(auth, protocol, clock, expires_in=ALMOST_EXPIRED)

    await clock.advance(CHECK_INTERVAL)
    await protocol.wait_for_sent(ProtoOAAccountAuthReq, count=2)

    assert publisher.only_of(ReadyEvent).trigger is AuthTrigger.INITIAL


async def test_a_store_that_cannot_save_aborts_the_refresh(
    auth: AuthManager,
    make_monitors: Callable[..., Monitors],
    protocol: StubProtocol,
    clock: ManualClock,
    publisher: RecordingPublisher,
) -> None:
    """Putting a token to use that storage never accepted would strand a restart."""
    store = RecordingStore(fail_first=1)
    make_monitors(token_store=store, check_interval=CHECK_INTERVAL)
    protocol.respond(ProtoOARefreshTokenReq, factories.refresh_token_res())
    await start_with_account(auth, protocol, clock, expires_in=ALMOST_EXPIRED)

    await clock.advance(CHECK_INTERVAL)
    await publisher.wait_for_type(TokenRefreshFailedEvent)

    failure = publisher.only_of(TokenRefreshFailedEvent)
    assert failure.account_id == factories.ACCOUNT_ID
    assert isinstance(failure.error.cause, RuntimeError)
    assert len(protocol.sent_of(ProtoOAAccountAuthReq)) == 1


async def test_a_transient_store_outage_recovers_on_the_next_check(
    auth: AuthManager,
    make_monitors: Callable[..., Monitors],
    protocol: StubProtocol,
    clock: ManualClock,
) -> None:
    store = RecordingStore(fail_first=1)
    make_monitors(token_store=store, check_interval=CHECK_INTERVAL)
    protocol.respond(ProtoOARefreshTokenReq, factories.refresh_token_res(expires_in=int(ALMOST_EXPIRED)))
    await start_with_account(auth, protocol, clock, expires_in=ALMOST_EXPIRED)

    await clock.advance(CHECK_INTERVAL)
    await store.wait_for(1)
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED)
    await clock.advance(CHECK_INTERVAL)
    await store.wait_for(2)

    assert protocol.sent_of(ProtoOAAccountAuthReq)[-1].access_token == "new-access-token"


async def test_an_account_the_server_confirms_is_gone_stops_being_authorized(
    auth: AuthManager,
    monitors: Monitors,
    protocol: StubProtocol,
    clock: ManualClock,
    publisher: RecordingPublisher,
) -> None:
    """A report the server stands behind is a real drop, and is published as one."""
    protocol.respond_in_sequence(
        ProtoOAAccountAuthReq,
        [factories.account_auth_res(), APIError(error_code="TEMPORARY")],
    )
    protocol.respond(ProtoOATraderReq, APIError(error_code="ACCOUNT_NOT_AUTHORIZED"))
    await auth.authenticate_trader(factories.credentials(expires_in=PLENTY_OF_TIME))
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED)

    await monitors.recovery.handle_account_disconnect(factories.ACCOUNT_ID)

    assert not auth.is_account_authorized(factories.ACCOUNT_ID)
    assert publisher.of(AccountDisconnectEvent) == [AccountDisconnectEvent(factories.ACCOUNT_ID)]


async def test_a_session_the_server_still_holds_is_left_alone(
    auth: AuthManager,
    monitors: Monitors,
    protocol: StubProtocol,
    clock: ManualClock,
    publisher: RecordingPublisher,
) -> None:
    """A token rotation makes the server report a disconnect it did not perform.

    Regression guard: taking that report at face value marked a working account
    unauthorized, published a drop that never happened, and left recovery
    retrying an account the server would only ever refuse as already logged in.
    Checking it by re-authorizing was no better, because the rotation that
    prompts the report is what makes that check answer wrongly.
    """
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())
    protocol.respond(ProtoOATraderReq, factories.trader_res())
    await auth.authenticate_trader(factories.credentials(expires_in=PLENTY_OF_TIME))
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED)

    await monitors.recovery.handle_account_disconnect(factories.ACCOUNT_ID)

    assert auth.is_account_authorized(factories.ACCOUNT_ID)
    assert publisher.of(AccountDisconnectEvent) == []
    assert publisher.of(ReadyEvent) == [ReadyEvent(factories.ACCOUNT_ID, AuthTrigger.INITIAL)]
    # Nothing re-authorized the account, so nothing could have disturbed the
    # session the report was wrong about.
    assert len(protocol.sent_of(ProtoOAAccountAuthReq)) == 1


async def test_a_check_that_cannot_be_answered_leaves_the_account_alone(
    auth: AuthManager,
    monitors: Monitors,
    protocol: StubProtocol,
    clock: ManualClock,
    publisher: RecordingPublisher,
) -> None:
    """Failing to ask is not the same as being told the session is gone.

    Regression guard: anything that stopped the check from completing used to
    count as confirmation, so a report that could not be checked took a working
    account out of service.
    """
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())
    protocol.respond(ProtoOATraderReq, CTraderConnectionTimeoutError(10.0, "request"))
    await auth.authenticate_trader(factories.credentials(expires_in=PLENTY_OF_TIME))
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED)

    await monitors.recovery.handle_account_disconnect(factories.ACCOUNT_ID)

    assert auth.is_account_authorized(factories.ACCOUNT_ID)
    assert publisher.of(AccountDisconnectEvent) == []


async def test_a_disconnect_reported_while_the_token_rotates_is_not_a_drop(
    auth: AuthManager,
    monitors: Monitors,
    protocol: StubProtocol,
    clock: ManualClock,
    publisher: RecordingPublisher,
    sessions: SessionStore,
) -> None:
    """The window a refresh opens is not a session anyone lost.

    Regression guard: the server reports a disconnect for the authorization a
    rotation replaces, and while the replacement is in flight the account is
    genuinely unauthorized — it refuses everything with INVALID_REQUEST. Asking
    it anything in that window and believing the answer published a drop for a
    session that was serving requests a moment later.
    """
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())
    protocol.respond(ProtoOATraderReq, APIError(error_code="INVALID_REQUEST"))
    await auth.authenticate_trader(factories.credentials(expires_in=PLENTY_OF_TIME))
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED)
    sessions.begin_refresh(factories.ACCOUNT_ID)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(monitors.recovery.handle_account_disconnect, factories.ACCOUNT_ID)
        await anyio.sleep(0.01)
        # Nothing has been decided while the rotation is in flight.
        assert publisher.of(AccountDisconnectEvent) == []
        assert not protocol.sent_of(ProtoOATraderReq)

        protocol.respond(ProtoOATraderReq, factories.trader_res())
        sessions.end_refresh(factories.ACCOUNT_ID)

    assert auth.is_account_authorized(factories.ACCOUNT_ID)
    assert publisher.of(AccountDisconnectEvent) == []
    assert len(protocol.sent_of(ProtoOATraderReq)) == 1


@pytest.mark.parametrize("error_code", ["OA_AUTH_TOKEN_EXPIRED", "CH_ACCESS_TOKEN_INVALID"])
async def test_a_check_refused_over_the_token_leaves_the_account_alone(
    error_code: str,
    auth: AuthManager,
    monitors: Monitors,
    protocol: StubProtocol,
    clock: ManualClock,
    publisher: RecordingPublisher,
) -> None:
    """A refusal naming the token says nothing about the session behind it.

    Regression guard: the server refuses everything for an account while a
    rotation is in flight, and the disconnect it reports for that same rotation
    arrives inside the window. Reading the refusal as an answer published a drop
    for a session that was still being served.
    """
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())
    protocol.respond(ProtoOATraderReq, APIError(error_code=error_code))
    await auth.authenticate_trader(factories.credentials(expires_in=PLENTY_OF_TIME))
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED)

    await monitors.recovery.handle_account_disconnect(factories.ACCOUNT_ID)

    assert auth.is_account_authorized(factories.ACCOUNT_ID)
    assert publisher.of(AccountDisconnectEvent) == []
    assert len(protocol.sent_of(ProtoOAAccountAuthReq)) == 1


async def test_a_disconnected_account_is_re_authenticated(
    auth: AuthManager,
    monitors: Monitors,
    protocol: StubProtocol,
    clock: ManualClock,
    publisher: RecordingPublisher,
) -> None:
    await start_with_account(auth, protocol, clock, expires_in=PLENTY_OF_TIME)
    protocol.respond(ProtoOATraderReq, APIError(error_code="ACCOUNT_NOT_AUTHORIZED"))

    await monitors.recovery.handle_account_disconnect(factories.ACCOUNT_ID)
    await publisher.wait_for_type(ReadyEvent, count=2)

    assert auth.is_account_authorized(factories.ACCOUNT_ID)
    assert publisher.of(ReadyEvent)[-1] == ReadyEvent(factories.ACCOUNT_ID, AuthTrigger.ACCOUNT_REAUTH)


async def test_recovery_keeps_trying_after_a_failure(
    auth: AuthManager,
    monitors: Monitors,
    protocol: StubProtocol,
    clock: ManualClock,
    publisher: RecordingPublisher,
) -> None:
    protocol.respond_in_sequence(
        ProtoOAAccountAuthReq,
        [
            factories.account_auth_res(),
            # The first recovery attempt after the drop is confirmed, then the
            # retry that succeeds.
            APIError(error_code="TEMPORARY"),
            factories.account_auth_res(),
        ],
    )
    protocol.respond(ProtoOATraderReq, APIError(error_code="ACCOUNT_NOT_AUTHORIZED"))
    await auth.authenticate_trader(factories.credentials(expires_in=PLENTY_OF_TIME))
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED)

    await monitors.recovery.handle_account_disconnect(factories.ACCOUNT_ID)
    # The failed attempt arms a backoff; time has to move for the retry.
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED + 1)
    await clock.advance(1.0)
    await publisher.wait_for_type(ReadyEvent, count=2)

    assert auth.is_account_authorized(factories.ACCOUNT_ID)


async def test_an_account_dropped_during_another_backoff_is_recovered_at_once(
    auth: AuthManager,
    make_monitors: Callable[..., Monitors],
    protocol: StubProtocol,
    clock: ManualClock,
    publisher: RecordingPublisher,
) -> None:
    """Backoff is per account, so a healthy account never queues behind a sick one."""
    stubborn = 111
    healthy = 222

    monitors = make_monitors(reauth_policy=ReauthPolicy(min_wait=10.0, max_wait=10.0))
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())
    await auth.authenticate_trader(factories.credentials(account_id=stubborn, expires_in=PLENTY_OF_TIME))
    await auth.authenticate_trader(factories.credentials(account_id=healthy, expires_in=PLENTY_OF_TIME))
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED)

    # From here the stubborn account can never re-authenticate.
    def answer(request: betterproto.Message) -> betterproto.Message | Exception:
        if isinstance(request, ProtoOAAccountAuthReq) and request.ctid_trader_account_id == stubborn:
            return APIError(error_code="TEMPORARY")
        return factories.account_auth_res()

    protocol.respond_with(ProtoOAAccountAuthReq, answer)
    # Both reports are real: the server no longer serves either account.
    protocol.respond(ProtoOATraderReq, APIError(error_code="ACCOUNT_NOT_AUTHORIZED"))

    await monitors.recovery.handle_account_disconnect(stubborn)
    # Its failed attempt parks recovery on a ten second backoff.
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED + 1)

    await monitors.recovery.handle_account_disconnect(healthy)
    # Recovery re-authorizes it without waiting out the stubborn account's backoff.
    await publisher.wait_for_type(ReadyEvent, count=3)

    assert auth.is_account_authorized(healthy)
    assert not auth.is_account_authorized(stubborn)


async def test_a_disconnect_for_an_unknown_account_is_ignored(
    auth: AuthManager,
    monitors: Monitors,
    protocol: StubProtocol,
    clock: ManualClock,
) -> None:
    await start_with_account(auth, protocol, clock, expires_in=PLENTY_OF_TIME)

    await monitors.recovery.handle_account_disconnect(999_999)
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED)

    assert len(protocol.sent_of(ProtoOAAccountAuthReq)) == 1
    assert auth.is_account_authorized(factories.ACCOUNT_ID)


async def test_a_report_for_an_account_already_recovering_is_not_checked_again(
    auth: AuthManager,
    protocol: StubProtocol,
    publisher: RecordingPublisher,
    sessions: SessionStore,
    clock: ManualClock,
) -> None:
    """Once a drop is confirmed, further reports say nothing the queue does not.

    The monitor is not served here: recovery's own retries would be
    indistinguishable from a second check of the same report.
    """
    recovery = SessionRecovery(store=sessions, authenticator=auth, publisher=publisher, clock=clock)
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())
    protocol.respond(ProtoOATraderReq, APIError(error_code="ACCOUNT_NOT_AUTHORIZED"))
    await auth.authenticate_trader(factories.credentials(expires_in=PLENTY_OF_TIME))

    await recovery.handle_account_disconnect(factories.ACCOUNT_ID)
    checked = len(protocol.sent_of(ProtoOATraderReq))
    await recovery.handle_account_disconnect(factories.ACCOUNT_ID)
    await recovery.handle_account_disconnect(factories.ACCOUNT_ID)

    assert len(protocol.sent_of(ProtoOATraderReq)) == checked
    assert publisher.of(AccountDisconnectEvent) == [AccountDisconnectEvent(factories.ACCOUNT_ID)]
