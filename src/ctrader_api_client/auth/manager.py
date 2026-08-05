"""Turning credentials into live sessions.

The manager owns the exchange that authorizes an account on the current link,
and nothing else: the token refresh loop lives in `_refresh`, session recovery
in `_recovery`, and the accounts themselves in `_session`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol as TypingProtocol

from .._internal.proto import (
    ProtoOAAccountAuthReq,
    ProtoOAAccountAuthRes,
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
)
from ..enums import AuthTrigger
from ..events import EventPublisher, ReadyEvent
from ..exceptions import (
    AccountAuthError,
    APIError,
    ApplicationAuthError,
    TokenExpiredError,
)
from ._session import SessionStore
from .credentials import AccountCredentials


if TYPE_CHECKING:
    from ..connection.protocol import Protocol


logger = logging.getLogger(__name__)


class SessionRestorer(TypingProtocol):
    """Whatever holds state that a fresh server-side session starts without."""

    async def restore(self, account_id: int) -> None:
        """Re-apply that state to the account's new session."""
        ...

    def forget(self, account_id: int) -> None:
        """Discard that state, because the account is no longer ours to restore."""
        ...


class AuthManager:
    """Authorizes trading accounts and answers for the sessions they hold.

    The application is authenticated by the client as it connects, so a caller
    only ever presents account credentials.

    Example:
        ```python
        async with client:
            await client.auth.authenticate_trader(credentials)
        ```
    """

    def __init__(
        self,
        protocol: Protocol,
        publisher: EventPublisher,
        client_id: str,
        client_secret: str,
        store: SessionStore | None = None,
        restorer: SessionRestorer | None = None,
    ) -> None:
        """Initialize the authentication manager.

        Args:
            protocol: The protocol instance for sending auth requests.
            publisher: Where ReadyEvent is published.
            client_id: OAuth client ID for the application.
            client_secret: OAuth client secret for the application.
            store: Where accounts and their session state are kept. Shared with
                the token refresher and the session recovery monitor.
            restorer: Re-applies whatever a fresh session starts without, before
                the account is announced as ready.
        """
        self._protocol = protocol
        self._publisher = publisher
        self._client_id = client_id
        self._client_secret = client_secret
        self._store = store if store is not None else SessionStore()
        self._restorer = restorer

        # Track app authentication state
        self._app_authenticated = False

    @property
    def is_app_authenticated(self) -> bool:
        """Whether the application has been authenticated."""
        return self._app_authenticated

    @property
    def authenticated_accounts(self) -> list[int]:
        """List of account IDs the manager holds credentials for."""
        return self._store.account_ids()

    @property
    def authorized_accounts(self) -> list[int]:
        """List of account IDs with a live, authorized server-side session."""
        return self._store.authorized_ids()

    def is_account_authorized(self, account_id: int) -> bool:
        """Whether the account currently has a live, authorized session.

        Returns False after a server-side account disconnect, or after the
        connection drops, until re-authentication succeeds.

        Args:
            account_id: The cTID trader account ID.
        """
        return self._store.is_authorized(account_id)

    def get_credentials(self, account_id: int) -> AccountCredentials | None:
        """Get credentials for an account.

        Args:
            account_id: The cTID trader account ID.

        Returns:
            The account credentials, or None if not authenticated.
        """
        return self._store.credentials(account_id)

    def all_credentials(self) -> list[AccountCredentials]:
        """Credentials for every account the manager holds, oldest first.

        Returns:
            A snapshot list, safe to iterate while accounts are added or removed.
        """
        return self._store.all_credentials()

    async def authenticate_app(self, timeout: float = 30.0) -> None:
        """Authenticate the application with cTrader.

        Called by the client as it connects, and again on every reconnect;
        nothing else can be authenticated until it succeeds.

        Args:
            timeout: Request timeout in seconds.

        Raises:
            ApplicationAuthError: If the server rejects the application credentials.
            CTraderConnectionTimeoutError: If request times out.
        """
        logger.debug("Authenticating application")

        request = ProtoOAApplicationAuthReq(
            client_id=self._client_id,
            client_secret=self._client_secret,
        )

        try:
            await self._protocol.request(request, ProtoOAApplicationAuthRes, timeout=timeout)
        except APIError as e:
            raise ApplicationAuthError(e.error_code, e.description) from e

        self._app_authenticated = True
        logger.debug("Application authenticated successfully")

    async def authenticate_trader(
        self,
        credentials: AccountCredentials,
        timeout: float = 30.0,
    ) -> None:
        """Authenticate a trading account and keep its session alive.

        The credentials are kept, so the tokens are refreshed before they
        expire and the session is re-established after a disconnect.

        Args:
            credentials: The account credentials including tokens.
            timeout: Request timeout in seconds.

        Raises:
            TokenExpiredError: If the access token has expired or the server
                rejects it as invalid.
            AccountAuthError: If the server rejects the account.
            CTraderConnectionTimeoutError: If request times out.
        """
        await self.establish(credentials, AuthTrigger.INITIAL, timeout=timeout)

    async def establish(
        self,
        credentials: AccountCredentials,
        trigger: AuthTrigger,
        timeout: float = 30.0,
    ) -> None:
        """Authorize an account, recording why so the right events follow.

        Args:
            credentials: The account credentials including tokens.
            trigger: Why the authentication is happening. Determines whether a
                ReadyEvent is published, so subscription restoration can be
                driven correctly (see AuthTrigger).
            timeout: Request timeout in seconds.

        Raises:
            TokenExpiredError: If the access token has expired or the server
                rejects it as invalid.
            AccountAuthError: If the server rejects the account.
            CTraderConnectionTimeoutError: If request times out.
        """
        if trigger is AuthTrigger.INITIAL:
            logger.debug("Authenticating account %d", credentials.account_id)
        else:
            logger.debug("Re-authenticating account %d (%s)", credentials.account_id, trigger.value)

        if credentials.is_expired():
            raise TokenExpiredError(credentials.account_id)

        request = ProtoOAAccountAuthReq(
            ctid_trader_account_id=credentials.account_id,
            access_token=credentials.access_token,
        )

        try:
            await self._protocol.request(request, ProtoOAAccountAuthRes, timeout=timeout)
        except APIError as e:
            if e.is_token_failure():
                raise TokenExpiredError(credentials.account_id) from e
            raise AccountAuthError(e.error_code, e.description, credentials.account_id) from e

        # Keep the credentials for refresh monitoring and mark the session live
        self._store.authorize(credentials)
        logger.debug("Account %d authenticated successfully", credentials.account_id)

        # A token refresh renews the session in place, so its subscriptions
        # survive and there is nothing for a consumer to reapply.
        if trigger is not AuthTrigger.TOKEN_REFRESH:
            if self._restorer is not None:
                await self._restorer.restore(credentials.account_id)
            await self._publisher.emit(ReadyEvent(account_id=credentials.account_id, trigger=trigger))

    def remove_account(self, account_id: int) -> bool:
        """Remove an account from refresh monitoring.

        Whatever was being held for restoration is discarded with it, since a
        session this manager will not re-establish is not one anything should
        be restored onto.

        Args:
            account_id: The cTID trader account ID.

        Returns:
            True if the account was removed, False if it wasn't registered.
        """
        if self._store.remove(account_id):
            if self._restorer is not None:
                self._restorer.forget(account_id)
            logger.debug("Account %d removed from auth manager", account_id)
            return True
        return False
