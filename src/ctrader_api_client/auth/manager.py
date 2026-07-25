from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import anyio
import anyio.abc
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .._internal.proto import (
    ProtoOAAccountAuthReq,
    ProtoOAAccountAuthRes,
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAGetAccountListByAccessTokenRes,
    ProtoOARefreshTokenReq,
    ProtoOARefreshTokenRes,
)
from ..exceptions import (
    AccountNotFoundError,
    APIError,
    TokenRefreshError,
)
from ..models import AccountSummary
from .credentials import AccountCredentials
from .trigger import AuthTrigger


if TYPE_CHECKING:
    from ..connection.protocol import Protocol


logger = logging.getLogger(__name__)

TokenRefreshCallback = Callable[[AccountCredentials], Awaitable[None]]
AccountReadyCallback = Callable[[int, AuthTrigger], Awaitable[None]]  # (account_id, trigger)


class AuthManager:
    """Manages authentication for cTrader API connections.

    Handles application authentication, account authentication for multiple
    trading accounts, and automatic token refresh before expiry.

    Example:
        ```python
        auth = AuthManager(
            protocol=protocol,
            client_id="your_client_id",
            client_secret="your_client_secret",
            on_tokens_refreshed=save_tokens_to_storage,
        )

        await auth.authenticate_app()
        await auth.authenticate_account(credentials)
        await auth.start()  # Start refresh monitor

        # ... trading operations ...

        await auth.stop()
        ```
    """

    def __init__(
        self,
        protocol: Protocol,
        client_id: str,
        client_secret: str,
        refresh_buffer_seconds: float = 300.0,
        refresh_check_interval: float = 60.0,
        refresh_retry_attempts: int = 3,
        refresh_retry_min_wait: float = 1.0,
        refresh_retry_max_wait: float = 30.0,
        reauth_retry_min_wait: float = 1.0,
        reauth_retry_max_wait: float = 60.0,
        on_tokens_refreshed: TokenRefreshCallback | None = None,
        on_account_ready: AccountReadyCallback | None = None,
    ) -> None:
        """Initialize the authentication manager.

        Args:
            protocol: The protocol instance for sending auth requests.
            client_id: OAuth client ID for the application.
            client_secret: OAuth client secret for the application.
            refresh_buffer_seconds: Refresh tokens this many seconds before expiry.
                Defaults to 300 (5 minutes).
            refresh_check_interval: How often to check for expiring tokens (seconds).
                Defaults to 60.
            refresh_retry_attempts: Max retry attempts for token refresh.
                Defaults to 3.
            refresh_retry_min_wait: Initial wait between retries (seconds).
                Defaults to 1.0.
            refresh_retry_max_wait: Maximum wait between retries (seconds).
                Defaults to 30.0.
            reauth_retry_min_wait: Initial backoff between account recovery
                re-auth attempts (seconds). Defaults to 1.0.
            reauth_retry_max_wait: Maximum backoff between account recovery
                re-auth attempts (seconds). Defaults to 60.0.
            on_tokens_refreshed: Async callback invoked when tokens are refreshed.
                Receives the new AccountCredentials. Use this to persist tokens.
            on_account_ready: Async callback invoked when an account is authenticated.
                Receives (account_id, trigger). Use this to perform any initial client setup.
        """
        self._protocol = protocol
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_buffer = refresh_buffer_seconds
        self._check_interval = refresh_check_interval
        self._retry_attempts = refresh_retry_attempts
        self._retry_min_wait = refresh_retry_min_wait
        self._retry_max_wait = refresh_retry_max_wait
        self._reauth_retry_min_wait = reauth_retry_min_wait
        self._reauth_retry_max_wait = reauth_retry_max_wait
        self._on_tokens_refreshed = on_tokens_refreshed
        self._on_account_ready = on_account_ready

        # Account storage
        self._accounts: dict[int, AccountCredentials] = {}

        # Accounts with a live, authorized server-side session
        self._authorized_accounts: set[int] = set()

        # Accounts awaiting recovery re-auth after a server-side disconnect
        self._pending_reauth: set[int] = set()
        self._reauth_signal = anyio.Event()

        # Background task management
        self._task_group: anyio.abc.TaskGroup | None = None
        self._task_scope: anyio.CancelScope | None = None
        self._running = False

        # Track app authentication state
        self._app_authenticated = False

    @property
    def is_app_authenticated(self) -> bool:
        """Whether the application has been authenticated."""
        return self._app_authenticated

    @property
    def authenticated_accounts(self) -> list[int]:
        """List of account IDs the manager holds credentials for."""
        return list(self._accounts.keys())

    @property
    def authorized_accounts(self) -> list[int]:
        """List of account IDs with a live, authorized server-side session."""
        return list(self._authorized_accounts)

    def is_account_authorized(self, account_id: int) -> bool:
        """Whether the account currently has a live, authorized session.

        Returns False after a server-side account disconnect until recovery
        re-authentication succeeds.

        Args:
            account_id: The cTID trader account ID.
        """
        return account_id in self._authorized_accounts

    def get_credentials(self, account_id: int) -> AccountCredentials | None:
        """Get credentials for an account.

        Args:
            account_id: The cTID trader account ID.

        Returns:
            The account credentials, or None if not authenticated.
        """
        return self._accounts.get(account_id)

    async def authenticate_app(self, timeout: float = 30.0) -> ProtoOAApplicationAuthRes:
        """Authenticate the application with cTrader.

        This must be called before authenticating any accounts.

        Args:
            timeout: Request timeout in seconds.

        Returns:
            The authentication response from the server.

        Raises:
            APIError: If authentication fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        logger.debug("Authenticating application")

        request = ProtoOAApplicationAuthReq(
            client_id=self._client_id,
            client_secret=self._client_secret,
        )

        response = await self._protocol.send_request(request, timeout=timeout)

        if not isinstance(response, ProtoOAApplicationAuthRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOAApplicationAuthRes, got {type(response).__name__}",
            )

        self._app_authenticated = True
        logger.debug("Application authenticated successfully")
        return response

    async def authenticate_account(
        self,
        credentials: AccountCredentials,
        timeout: float = 30.0,
        trigger: AuthTrigger = AuthTrigger.INITIAL,
    ) -> ProtoOAAccountAuthRes:
        """Authenticate a trading account.

        The account credentials are stored for automatic token refresh.

        Args:
            credentials: The account credentials including tokens.
            timeout: Request timeout in seconds.
            trigger: Why the authentication is happening. Threaded through to
                the account-ready callback so subscription restoration can be
                driven correctly (see AuthTrigger).

        Returns:
            The authentication response from the server.

        Raises:
            APIError: If authentication fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        if trigger is AuthTrigger.INITIAL:
            logger.debug("Authenticating account %d", credentials.account_id)
        else:
            logger.debug("Re-authenticating account %d (%s)", credentials.account_id, trigger.value)

        request = ProtoOAAccountAuthReq(
            ctid_trader_account_id=credentials.account_id,
            access_token=credentials.access_token,
        )

        response = await self._protocol.send_request(request, timeout=timeout)

        if not isinstance(response, ProtoOAAccountAuthRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOAAccountAuthRes, got {type(response).__name__}",
            )

        # Store credentials for refresh monitoring and mark the session live
        self._accounts[credentials.account_id] = credentials
        self._authorized_accounts.add(credentials.account_id)
        self._pending_reauth.discard(credentials.account_id)
        logger.debug("Account %d authenticated successfully", credentials.account_id)

        # Notify callback
        if self._on_account_ready is not None:
            try:
                await self._on_account_ready(credentials.account_id, trigger)
            except Exception as e:
                logger.warning(
                    "Account ready callback failed for account %d: %s",
                    credentials.account_id,
                    e,
                )

        return response

    async def get_accounts(
        self,
        access_token: str,
        timeout: float = 30.0,
    ) -> list[AccountSummary]:
        """Get all trading accounts associated with an access token.

        This retrieves the list of accounts without authenticating them.
        Useful for discovering available accounts or letting users select
        which account to use.

        Args:
            access_token: OAuth access token.
            timeout: Request timeout in seconds.

        Returns:
            List of account summaries (lightweight account info).

        Raises:
            APIError: If the request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        logger.debug("Fetching accounts for access token")

        request = ProtoOAGetAccountListByAccessTokenReq(
            access_token=access_token,
        )

        response = await self._protocol.send_request(request, timeout=timeout)

        if not isinstance(response, ProtoOAGetAccountListByAccessTokenRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOAGetAccountListByAccessTokenRes, got {type(response).__name__}",
            )

        accounts = [AccountSummary.from_proto(acc) for acc in response.ctid_trader_account]
        logger.debug("Found %d accounts", len(accounts))
        return accounts

    async def resolve_account_id(
        self,
        access_token: str,
        trader_login: int,
        timeout: float = 30.0,
    ) -> int:
        """Resolve a trader login to its cTID trader account ID.

        Args:
            access_token: OAuth access token.
            trader_login: The trader login number (visible in cTrader app).
            timeout: Request timeout in seconds.

        Returns:
            The cTID trader account ID (used for API calls).

        Raises:
            AccountNotFoundError: If no account matches the trader login.
            APIError: If the request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        accounts = await self.get_accounts(access_token, timeout=timeout)

        for account in accounts:
            if account.trader_login == trader_login:
                logger.debug(
                    "Resolved trader login %d to account ID %d",
                    trader_login,
                    account.account_id,
                )
                return account.account_id

        available_logins = [acc.trader_login for acc in accounts]
        raise AccountNotFoundError(trader_login, available_logins)

    async def authenticate_by_trader_login(
        self,
        trader_login: int,
        access_token: str,
        refresh_token: str,
        expires_at: float,
        timeout: float = 30.0,
    ) -> AccountCredentials:
        """Authenticate an account using trader login (discovers cTID automatically).

        This is a convenience method that:
        1. Resolves the trader login to the cTID trader account ID
        2. Creates AccountCredentials with the resolved ID
        3. Authenticates the account

        Args:
            trader_login: The trader login number (visible in cTrader app).
            access_token: OAuth access token.
            refresh_token: OAuth refresh token.
            expires_at: Unix timestamp when access token expires.
            timeout: Request timeout in seconds.

        Returns:
            AccountCredentials with the resolved account_id, ready for use.

        Raises:
            AccountNotFoundError: If no account matches the trader login.
            APIError: If authentication fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        logger.debug("Authenticating by trader login %d", trader_login)

        # Resolve trader_login to account_id
        account_id = await self.resolve_account_id(access_token, trader_login, timeout=timeout)

        # Create credentials with resolved ID
        credentials = AccountCredentials(
            account_id=account_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )

        # Authenticate the account
        await self.authenticate_account(credentials, timeout=timeout)

        return credentials

    def remove_account(self, account_id: int) -> bool:
        """Remove an account from refresh monitoring.

        Args:
            account_id: The cTID trader account ID.

        Returns:
            True if the account was removed, False if it wasn't registered.
        """
        if account_id in self._accounts:
            del self._accounts[account_id]
            self._authorized_accounts.discard(account_id)
            self._pending_reauth.discard(account_id)
            logger.debug("Account %d removed from auth manager", account_id)
            return True
        return False

    def handle_account_disconnect(self, account_id: int) -> None:
        """Handle a server-side account disconnect.

        Marks the account's session as no longer authorized and schedules
        recovery re-authentication on the existing connection. Idempotent while
        a recovery is already pending for the account.

        Args:
            account_id: The cTID trader account ID reported as disconnected.
        """
        if account_id not in self._accounts:
            return

        self._authorized_accounts.discard(account_id)

        if account_id in self._pending_reauth:
            return

        self._pending_reauth.add(account_id)
        self._reauth_signal.set()
        logger.warning(
            "Account %d disconnected by server; scheduling re-authentication",
            account_id,
        )

    async def start(self) -> None:
        """Start the background monitors.

        Runs the token refresh monitor and the account recovery monitor, which
        re-authenticates accounts dropped by a server-side disconnect.
        """
        if self._running:
            return

        self._running = True
        self._task_group = anyio.create_task_group()
        await self._task_group.__aenter__()
        self._task_group.start_soon(self._refresh_loop)
        self._task_group.start_soon(self._reauth_loop)
        logger.debug("Auth monitors started")

    async def stop(self) -> None:
        """Stop the background monitors."""
        self._running = False

        if self._task_scope is not None:
            self._task_scope.cancel()

        if self._task_group is not None:
            self._task_group.cancel_scope.cancel()
            try:
                await self._task_group.__aexit__(None, None, None)
            except Exception:
                pass
            self._task_group = None

        self._authorized_accounts.clear()
        self._pending_reauth.clear()

        logger.debug("Auth monitors stopped")

    async def _reauth_loop(self) -> None:
        """Recover accounts dropped by a server-side account disconnect.

        Waits for accounts flagged by handle_account_disconnect, then
        re-authenticates them on the existing connection with capped
        exponential backoff, retrying indefinitely until each succeeds or the
        manager stops. A successful re-auth restores authorized state and emits
        a ReadyEvent so subscriptions can be restored.
        """
        while self._running:
            await self._reauth_signal.wait()
            self._reauth_signal = anyio.Event()

            backoff = self._reauth_retry_min_wait
            while self._running and self._pending_reauth:
                recovered_any = False
                for account_id in list(self._pending_reauth):
                    credentials = self._accounts.get(account_id)
                    if credentials is None:
                        self._pending_reauth.discard(account_id)
                        continue
                    try:
                        await self.authenticate_account(credentials, trigger=AuthTrigger.ACCOUNT_REAUTH)
                        recovered_any = True
                    except Exception as e:
                        logger.warning(
                            "Recovery re-authentication for account %d failed, will retry: %s",
                            account_id,
                            e,
                        )

                if not self._pending_reauth:
                    break

                if recovered_any:
                    backoff = self._reauth_retry_min_wait
                await anyio.sleep(backoff)
                backoff = min(backoff * 2, self._reauth_retry_max_wait)

    async def _refresh_loop(self) -> None:
        """Periodically check and refresh expiring tokens."""
        with anyio.CancelScope() as scope:
            self._task_scope = scope
            while self._running:
                await anyio.sleep(self._check_interval)

                for account_id in list(self._accounts.keys()):
                    credentials = self._accounts.get(account_id)
                    if credentials is None:
                        continue

                    if credentials.expires_soon(self._refresh_buffer):
                        logger.debug(
                            "Token for account %d expires soon (%.0fs remaining), refreshing",
                            account_id,
                            credentials.time_until_expiry(),
                        )
                        try:
                            await self._refresh_account(account_id)
                        except TokenRefreshError as e:
                            logger.error("Failed to refresh token for account %d: %s", account_id, e)
                            raise

    async def _refresh_account(self, account_id: int) -> None:
        """Refresh tokens for an account with retry logic.

        Args:
            account_id: The cTID trader account ID.

        Raises:
            TokenRefreshError: If refresh fails after all retries.
        """
        credentials = self._accounts.get(account_id)
        if credentials is None:
            return

        last_error: Exception | None = None

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._retry_attempts),
                wait=wait_exponential(
                    min=self._retry_min_wait,
                    max=self._retry_max_wait,
                ),
                retry=retry_if_exception_type(APIError),
                reraise=True,
            ):
                with attempt:
                    logger.debug(
                        "Token refresh attempt %d/%d for account %d",
                        attempt.retry_state.attempt_number,
                        self._retry_attempts,
                        account_id,
                    )

                    # Send refresh request
                    request = ProtoOARefreshTokenReq(
                        refresh_token=credentials.refresh_token,
                    )
                    response = await self._protocol.send_request(request)

                    if not isinstance(response, ProtoOARefreshTokenRes):
                        raise APIError(
                            error_code="UNEXPECTED_RESPONSE",
                            description=f"Expected ProtoOARefreshTokenRes, got {type(response).__name__}",
                        )

                    # Update credentials
                    new_credentials = credentials.with_refreshed_tokens(
                        access_token=response.access_token,
                        refresh_token=response.refresh_token,
                        expires_in=response.expires_in,
                    )
                    self._accounts[account_id] = new_credentials

                    logger.debug(
                        "Token refreshed for account %d, new expiry in %ds",
                        account_id,
                        response.expires_in,
                    )

                    # Re-authenticate the account with the new token
                    await self.authenticate_account(new_credentials, trigger=AuthTrigger.TOKEN_REFRESH)

                    # Notify callback
                    if self._on_tokens_refreshed is not None:
                        try:
                            await self._on_tokens_refreshed(new_credentials)
                        except Exception as e:
                            logger.warning(
                                "Token refresh callback failed for account %d: %s",
                                account_id,
                                e,
                            )

        except APIError as e:
            last_error = e
        except Exception as e:
            last_error = e

        if last_error is not None:
            raise TokenRefreshError(account_id, last_error)
