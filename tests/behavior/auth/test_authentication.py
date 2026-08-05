"""Authenticating the application and individual trading accounts."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from ctrader_api_client._internal.proto import (
    ProtoOAAccountAuthReq,
    ProtoOAApplicationAuthReq,
)
from ctrader_api_client.auth import AuthManager
from ctrader_api_client.enums import AuthTrigger
from ctrader_api_client.events import ReadyEvent
from ctrader_api_client.exceptions import (
    AccountAuthError,
    APIError,
    ApplicationAuthError,
    TokenExpiredError,
)

from ...harness import RecordingPublisher, RecordingRestorer, StubProtocol, factories


async def test_the_application_reports_itself_authenticated(auth: AuthManager, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOAApplicationAuthReq, factories.app_auth_res())

    await auth.authenticate_app()

    assert auth.is_app_authenticated


async def test_the_application_sends_its_configured_credentials(
    auth: AuthManager,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOAApplicationAuthReq, factories.app_auth_res())

    await auth.authenticate_app()

    request = protocol.only_sent(ProtoOAApplicationAuthReq)
    assert (request.client_id, request.client_secret) == ("test-client-id", "test-client-secret")


async def test_a_failed_application_auth_leaves_the_app_unauthenticated(
    auth: AuthManager,
    protocol: StubProtocol,
) -> None:
    protocol.respond(
        ProtoOAApplicationAuthReq,
        APIError(error_code="CH_CLIENT_AUTH_FAILURE", description="bad credentials"),
    )

    with pytest.raises(ApplicationAuthError) as exc_info:
        await auth.authenticate_app()

    assert exc_info.value.error_code == "CH_CLIENT_AUTH_FAILURE"
    assert exc_info.value.description == "bad credentials"
    assert not auth.is_app_authenticated


async def test_an_unexpected_reply_to_application_auth_is_an_error(
    auth: AuthManager,
    protocol: StubProtocol,
) -> None:
    """A reply of the wrong type means the request was not honoured."""
    protocol.respond(ProtoOAApplicationAuthReq, factories.account_auth_res())

    with pytest.raises(ApplicationAuthError) as exc_info:
        await auth.authenticate_app()

    assert exc_info.value.error_code == "UNEXPECTED_RESPONSE"
    assert not auth.is_app_authenticated


async def test_an_authenticated_account_becomes_authorized(auth: AuthManager, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())

    await auth.authenticate_trader(factories.credentials())

    assert auth.is_account_authorized(factories.ACCOUNT_ID)
    assert auth.authorized_accounts == [factories.ACCOUNT_ID]
    assert auth.authenticated_accounts == [factories.ACCOUNT_ID]


async def test_account_auth_sends_the_account_id_and_token(auth: AuthManager, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())

    await auth.authenticate_trader(factories.credentials())

    request = protocol.only_sent(ProtoOAAccountAuthReq)
    assert request.ctid_trader_account_id == factories.ACCOUNT_ID
    assert request.access_token == factories.ACCESS_TOKEN


async def test_credentials_are_kept_for_later_use(auth: AuthManager, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())
    credentials = factories.credentials()

    await auth.authenticate_trader(credentials)

    assert auth.get_credentials(factories.ACCOUNT_ID) == credentials


async def test_an_unknown_account_has_no_credentials(auth: AuthManager) -> None:
    assert auth.get_credentials(factories.ACCOUNT_ID) is None
    assert not auth.is_account_authorized(factories.ACCOUNT_ID)


async def test_a_failed_account_auth_leaves_the_account_unauthorized(
    auth: AuthManager,
    protocol: StubProtocol,
) -> None:
    protocol.respond(
        ProtoOAAccountAuthReq,
        APIError(error_code="ACCOUNT_NOT_AUTHORIZED", description="not yours"),
    )

    with pytest.raises(AccountAuthError) as exc_info:
        await auth.authenticate_trader(factories.credentials())

    assert exc_info.value.error_code == "ACCOUNT_NOT_AUTHORIZED"
    assert exc_info.value.ctid_trader_account_id == factories.ACCOUNT_ID
    assert not auth.is_account_authorized(factories.ACCOUNT_ID)
    assert auth.get_credentials(factories.ACCOUNT_ID) is None


async def test_an_unexpected_reply_to_account_auth_is_an_error(
    auth: AuthManager,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOAAccountAuthReq, factories.app_auth_res())

    with pytest.raises(AccountAuthError) as exc_info:
        await auth.authenticate_trader(factories.credentials())

    assert exc_info.value.error_code == "UNEXPECTED_RESPONSE"
    assert not auth.is_account_authorized(factories.ACCOUNT_ID)


@pytest.mark.parametrize("error_code", ["OA_AUTH_TOKEN_EXPIRED", "CH_ACCESS_TOKEN_INVALID"])
async def test_a_rejected_token_is_reported_as_expired(
    auth: AuthManager,
    protocol: StubProtocol,
    error_code: str,
) -> None:
    """A dead token needs a refresh, not a retry, so it gets its own type."""
    protocol.respond(ProtoOAAccountAuthReq, APIError(error_code=error_code))

    with pytest.raises(TokenExpiredError) as exc_info:
        await auth.authenticate_trader(factories.credentials())

    assert exc_info.value.ctid_trader_account_id == factories.ACCOUNT_ID
    assert not auth.is_account_authorized(factories.ACCOUNT_ID)


async def test_an_already_expired_token_is_not_sent_to_the_server(
    auth: AuthManager,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())

    with pytest.raises(TokenExpiredError):
        await auth.authenticate_trader(factories.credentials(expires_in=-1.0))

    assert protocol.sent_of(ProtoOAAccountAuthReq) == []
    assert not auth.is_account_authorized(factories.ACCOUNT_ID)


async def test_an_authenticated_account_announces_itself(
    auth: AuthManager,
    protocol: StubProtocol,
    publisher: RecordingPublisher,
) -> None:
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())

    await auth.authenticate_trader(factories.credentials())

    assert publisher.only_of(ReadyEvent) == ReadyEvent(factories.ACCOUNT_ID, AuthTrigger.INITIAL)


async def test_the_reason_for_authentication_is_reported(
    auth: AuthManager,
    protocol: StubProtocol,
    publisher: RecordingPublisher,
) -> None:
    """Subscription restoration depends on knowing why the account came up."""
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())

    await auth.establish(factories.credentials(), AuthTrigger.RECONNECT)

    assert publisher.only_of(ReadyEvent) == ReadyEvent(factories.ACCOUNT_ID, AuthTrigger.RECONNECT)


async def test_a_session_is_restored_before_the_account_is_announced(
    make_auth: Callable[..., AuthManager],
    protocol: StubProtocol,
    publisher: RecordingPublisher,
) -> None:
    """A ready handler must not race a half-restored feed."""
    announced_when_restoring: list[int] = []
    restorer = RecordingRestorer(before_each=lambda: announced_when_restoring.append(len(publisher.of(ReadyEvent))))
    auth = make_auth(restorer=restorer)
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())

    await auth.establish(factories.credentials(), AuthTrigger.RECONNECT)

    assert restorer.restored == [factories.ACCOUNT_ID]
    assert announced_when_restoring == [0]


async def test_a_token_refresh_does_not_restore_the_session(
    make_auth: Callable[..., AuthManager],
    protocol: StubProtocol,
) -> None:
    """The session is renewed in place, so its subscriptions are still live."""
    restorer = RecordingRestorer()
    auth = make_auth(restorer=restorer)
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())

    await auth.establish(factories.credentials(), AuthTrigger.TOKEN_REFRESH)

    assert restorer.restored == []


async def test_a_removed_account_is_forgotten(auth: AuthManager, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())
    await auth.authenticate_trader(factories.credentials())

    removed = auth.remove_account(factories.ACCOUNT_ID)

    assert removed is True
    assert auth.authenticated_accounts == []
    assert not auth.is_account_authorized(factories.ACCOUNT_ID)


async def test_removing_an_account_discards_what_was_held_for_restoration(
    make_auth: Callable[..., AuthManager],
    protocol: StubProtocol,
) -> None:
    """State kept for a session nobody will re-establish is state nobody wants."""
    restorer = RecordingRestorer()
    auth = make_auth(restorer=restorer)
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())
    await auth.authenticate_trader(factories.credentials())

    auth.remove_account(factories.ACCOUNT_ID)

    assert restorer.forgotten == [factories.ACCOUNT_ID]


async def test_removing_an_unknown_account_holds_on_to_nothing(
    make_auth: Callable[..., AuthManager],
) -> None:
    """Nothing was removed, so there is nothing to discard on its behalf."""
    restorer = RecordingRestorer()
    auth = make_auth(restorer=restorer)

    assert auth.remove_account(factories.ACCOUNT_ID) is False
    assert restorer.forgotten == []


async def test_removing_an_unknown_account_reports_nothing_was_removed(auth: AuthManager) -> None:
    assert auth.remove_account(factories.ACCOUNT_ID) is False
