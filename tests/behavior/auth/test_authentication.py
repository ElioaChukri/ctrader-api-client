"""Authenticating the application and individual trading accounts."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from ctrader_api_client._internal.proto import (
    ProtoOAAccountAuthReq,
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAGetAccountListByAccessTokenReq,
)
from ctrader_api_client.auth import AuthManager, AuthTrigger
from ctrader_api_client.exceptions import (
    AccountAuthError,
    AccountNotFoundError,
    APIError,
    ApplicationAuthError,
    TokenExpiredError,
)

from ...harness import FailingRecorder, Recorder, StubProtocol, factories


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

    await auth.authenticate_account(factories.credentials())

    assert auth.is_account_authorized(factories.ACCOUNT_ID)
    assert auth.authorized_accounts == [factories.ACCOUNT_ID]
    assert auth.authenticated_accounts == [factories.ACCOUNT_ID]


async def test_account_auth_sends_the_account_id_and_token(auth: AuthManager, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())

    await auth.authenticate_account(factories.credentials())

    request = protocol.only_sent(ProtoOAAccountAuthReq)
    assert request.ctid_trader_account_id == factories.ACCOUNT_ID
    assert request.access_token == factories.ACCESS_TOKEN


async def test_credentials_are_kept_for_later_use(auth: AuthManager, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())
    credentials = factories.credentials()

    await auth.authenticate_account(credentials)

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
        await auth.authenticate_account(factories.credentials())

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
        await auth.authenticate_account(factories.credentials())

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
        await auth.authenticate_account(factories.credentials())

    assert exc_info.value.ctid_trader_account_id == factories.ACCOUNT_ID
    assert not auth.is_account_authorized(factories.ACCOUNT_ID)


async def test_an_already_expired_token_is_not_sent_to_the_server(
    auth: AuthManager,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())

    with pytest.raises(TokenExpiredError):
        await auth.authenticate_account(factories.credentials(expires_in=-1.0))

    assert protocol.sent_of(ProtoOAAccountAuthReq) == []
    assert not auth.is_account_authorized(factories.ACCOUNT_ID)


async def test_an_authenticated_account_announces_itself(
    make_auth: Callable[..., AuthManager],
    protocol: StubProtocol,
) -> None:
    ready: Recorder[tuple[int, AuthTrigger]] = Recorder()
    auth = make_auth(on_account_ready=ready)
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())

    await auth.authenticate_account(factories.credentials())

    assert ready.only == (factories.ACCOUNT_ID, AuthTrigger.INITIAL)


async def test_the_reason_for_authentication_is_reported(
    make_auth: Callable[..., AuthManager],
    protocol: StubProtocol,
) -> None:
    """Subscription restoration depends on knowing why the account came up."""
    ready: Recorder[tuple[int, AuthTrigger]] = Recorder()
    auth = make_auth(on_account_ready=ready)
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())

    await auth.authenticate_account(factories.credentials(), trigger=AuthTrigger.RECONNECT)

    assert ready.only == (factories.ACCOUNT_ID, AuthTrigger.RECONNECT)


async def test_a_failing_ready_callback_does_not_fail_the_authentication(
    make_auth: Callable[..., AuthManager],
    protocol: StubProtocol,
) -> None:
    ready: FailingRecorder[tuple[int, AuthTrigger]] = FailingRecorder()
    auth = make_auth(on_account_ready=ready)
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())

    await auth.authenticate_account(factories.credentials())

    assert auth.is_account_authorized(factories.ACCOUNT_ID)


async def test_accounts_are_listed_for_an_access_token(auth: AuthManager, protocol: StubProtocol) -> None:
    protocol.respond(
        ProtoOAGetAccountListByAccessTokenReq,
        factories.account_list_res(
            factories.ctid_account(account_id=1, trader_login=111),
            factories.ctid_account(account_id=2, trader_login=222),
        ),
    )

    accounts = await auth.get_accounts(factories.ACCESS_TOKEN)

    assert [account.account_id for account in accounts] == [1, 2]
    assert [account.trader_login for account in accounts] == [111, 222]


async def test_a_trader_login_resolves_to_its_account_id(auth: AuthManager, protocol: StubProtocol) -> None:
    protocol.respond(
        ProtoOAGetAccountListByAccessTokenReq,
        factories.account_list_res(
            factories.ctid_account(account_id=1, trader_login=111),
            factories.ctid_account(account_id=2, trader_login=222),
        ),
    )

    account_id = await auth.resolve_account_id(factories.ACCESS_TOKEN, trader_login=222)

    assert account_id == 2


async def test_an_unknown_trader_login_reports_what_is_available(
    auth: AuthManager,
    protocol: StubProtocol,
) -> None:
    """The caller most likely typed the wrong login, so name the ones that exist."""
    protocol.respond(
        ProtoOAGetAccountListByAccessTokenReq,
        factories.account_list_res(
            factories.ctid_account(account_id=1, trader_login=111),
            factories.ctid_account(account_id=2, trader_login=222),
        ),
    )

    with pytest.raises(AccountNotFoundError) as exc_info:
        await auth.resolve_account_id(factories.ACCESS_TOKEN, trader_login=999)

    assert exc_info.value.trader_login == 999
    assert exc_info.value.available_logins == [111, 222]
    assert "111" in str(exc_info.value)


async def test_authenticating_by_trader_login_returns_usable_credentials(
    auth: AuthManager,
    protocol: StubProtocol,
) -> None:
    protocol.respond(
        ProtoOAGetAccountListByAccessTokenReq,
        factories.account_list_res(factories.ctid_account(account_id=777, trader_login=222)),
    )
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res(account_id=777))

    credentials = await auth.authenticate_by_trader_login(
        trader_login=222,
        access_token=factories.ACCESS_TOKEN,
        refresh_token=factories.REFRESH_TOKEN,
        expires_at=1_900_000_000.0,
    )

    assert credentials.account_id == 777
    assert auth.is_account_authorized(777)


async def test_authenticating_by_an_unknown_login_sends_no_account_auth(
    auth: AuthManager,
    protocol: StubProtocol,
) -> None:
    protocol.respond(
        ProtoOAGetAccountListByAccessTokenReq,
        factories.account_list_res(factories.ctid_account(account_id=1, trader_login=111)),
    )

    with pytest.raises(AccountNotFoundError):
        await auth.authenticate_by_trader_login(
            trader_login=999,
            access_token=factories.ACCESS_TOKEN,
            refresh_token=factories.REFRESH_TOKEN,
            expires_at=1_900_000_000.0,
        )

    assert protocol.sent_of(ProtoOAAccountAuthReq) == []


async def test_an_unexpected_reply_to_the_account_list_is_an_error(
    auth: AuthManager,
    protocol: StubProtocol,
) -> None:
    protocol.respond(ProtoOAGetAccountListByAccessTokenReq, ProtoOAApplicationAuthRes())

    with pytest.raises(APIError) as exc_info:
        await auth.get_accounts(factories.ACCESS_TOKEN)

    assert exc_info.value.error_code == "UNEXPECTED_RESPONSE"


async def test_listing_accounts_with_a_dead_token_reports_it_as_expired(
    auth: AuthManager,
    protocol: StubProtocol,
) -> None:
    protocol.respond(
        ProtoOAGetAccountListByAccessTokenReq,
        APIError(error_code="CH_ACCESS_TOKEN_INVALID"),
    )

    with pytest.raises(TokenExpiredError):
        await auth.get_accounts(factories.ACCESS_TOKEN)


async def test_listing_accounts_surfaces_other_failures_unchanged(
    auth: AuthManager,
    protocol: StubProtocol,
) -> None:
    protocol.respond(
        ProtoOAGetAccountListByAccessTokenReq,
        APIError(error_code="CH_OA_CLIENT_NOT_FOUND"),
    )

    with pytest.raises(APIError) as exc_info:
        await auth.get_accounts(factories.ACCESS_TOKEN)

    assert exc_info.value.error_code == "CH_OA_CLIENT_NOT_FOUND"


async def test_a_removed_account_is_forgotten(auth: AuthManager, protocol: StubProtocol) -> None:
    protocol.respond(ProtoOAAccountAuthReq, factories.account_auth_res())
    await auth.authenticate_account(factories.credentials())

    removed = auth.remove_account(factories.ACCOUNT_ID)

    assert removed is True
    assert auth.authenticated_accounts == []
    assert not auth.is_account_authorized(factories.ACCOUNT_ID)


async def test_removing_an_unknown_account_reports_nothing_was_removed(auth: AuthManager) -> None:
    assert auth.remove_account(factories.ACCOUNT_ID) is False
