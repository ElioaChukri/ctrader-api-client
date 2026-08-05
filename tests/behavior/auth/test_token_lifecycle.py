"""Keeping accounts usable: token refresh and recovery after a server disconnect."""

from __future__ import annotations

from collections.abc import Callable

import betterproto
import pytest

from ctrader_api_client._internal.proto import ProtoOAAccountAuthReq, ProtoOARefreshTokenReq
from ctrader_api_client.auth import AuthManager, ReauthPolicy
from ctrader_api_client.enums import AuthTrigger
from ctrader_api_client.events import ReadyEvent, TokenRefreshFailedEvent
from ctrader_api_client.exceptions import APIError, TokenExpiredError

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


async def test_a_disconnected_account_stops_being_authorized(
    auth: AuthManager,
    monitors: Monitors,
    protocol: StubProtocol,
    clock: ManualClock,
) -> None:
    await start_with_account(auth, protocol, clock, expires_in=PLENTY_OF_TIME)

    monitors.recovery.handle_account_disconnect(factories.ACCOUNT_ID)

    assert not auth.is_account_authorized(factories.ACCOUNT_ID)


async def test_a_disconnected_account_is_re_authenticated(
    auth: AuthManager,
    monitors: Monitors,
    protocol: StubProtocol,
    clock: ManualClock,
    publisher: RecordingPublisher,
) -> None:
    await start_with_account(auth, protocol, clock, expires_in=PLENTY_OF_TIME)

    monitors.recovery.handle_account_disconnect(factories.ACCOUNT_ID)
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
            APIError(error_code="TEMPORARY"),
            factories.account_auth_res(),
        ],
    )
    await auth.authenticate_trader(factories.credentials(expires_in=PLENTY_OF_TIME))
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED)

    monitors.recovery.handle_account_disconnect(factories.ACCOUNT_ID)
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

    monitors.recovery.handle_account_disconnect(stubborn)
    # Its failed attempt parks recovery on a ten second backoff.
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED + 1)

    monitors.recovery.handle_account_disconnect(healthy)
    await protocol.wait_for_sent(ProtoOAAccountAuthReq, count=4)

    assert auth.is_account_authorized(healthy)
    assert not auth.is_account_authorized(stubborn)


async def test_a_disconnect_for_an_unknown_account_is_ignored(
    auth: AuthManager,
    monitors: Monitors,
    protocol: StubProtocol,
    clock: ManualClock,
) -> None:
    await start_with_account(auth, protocol, clock, expires_in=PLENTY_OF_TIME)

    monitors.recovery.handle_account_disconnect(999_999)
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED)

    assert len(protocol.sent_of(ProtoOAAccountAuthReq)) == 1
    assert auth.is_account_authorized(factories.ACCOUNT_ID)


async def test_repeated_disconnect_reports_do_not_stack_up_recoveries(
    auth: AuthManager,
    monitors: Monitors,
    protocol: StubProtocol,
    clock: ManualClock,
    publisher: RecordingPublisher,
) -> None:
    await start_with_account(auth, protocol, clock, expires_in=PLENTY_OF_TIME)

    monitors.recovery.handle_account_disconnect(factories.ACCOUNT_ID)
    monitors.recovery.handle_account_disconnect(factories.ACCOUNT_ID)
    monitors.recovery.handle_account_disconnect(factories.ACCOUNT_ID)
    await publisher.wait_for_type(ReadyEvent, count=2)
    await clock.wait_for_sleepers(SLEEPERS_WHEN_STARTED)

    assert len(protocol.sent_of(ProtoOAAccountAuthReq)) == 2
