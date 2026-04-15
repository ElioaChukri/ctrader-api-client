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


if TYPE_CHECKING:
    from ..connection.protocol import Protocol


logger = logging.getLogger(__name__)

TokenRefreshCallback = Callable[[AccountCredentials], Awaitable[None]]
AccountReadyCallback = Callable[[int, bool, bool], Awaitable[None]]  # (account_id, is_reconnect, is_reauth)


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
            on_tokens_refreshed: Async callback invoked when tokens are refreshed.
                Receives the new AccountCredentials. Use this to persist tokens.
            on_account_ready: Async callback invoked when an account is authenticated.
                Receives (account_id, is_reconnect). Use this to perform any initial client setup.
        """
        self._protocol = protocol
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_buffer = refresh_buffer_seconds
        self._check_interval = refresh_check_interval
        self._retry_attempts = refresh_retry_attempts
        self._retry_min_wait = refresh_retry_min_wait
        self._retry_max_wait = refresh_retry_max_wait
        self._on_tokens_refreshed = on_tokens_refreshed
        self._on_account_ready = on_account_ready

        # Account storage
        self._accounts: dict[int, AccountCredentials] = {}

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
        """List of authenticated account IDs."""
        return list(self._accounts.keys())

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
        logger.info("Authenticating application")

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
        logger.info("Application authenticated successfully")
        return response

    async def authenticate_account(
        self, credentials: AccountCredentials, timeout: float = 30.0, reauth: bool = False, reconnect: bool = False
    ) -> ProtoOAAccountAuthRes:
        """Authenticate a trading account.

        The account credentials are stored for automatic token refresh.

        Args:
            credentials: The account credentials including tokens.
            timeout: Request timeout in seconds.
            reauth: Whether this is a re-authentication (token refresh) or initial auth.
            reconnect: Whether this authentication is happening during a connection reconnect. This can be used
                to differentiate between a token refresh and a full reconnect scenario in the account ready callback.

        Returns:
            The authentication response from the server.

        Raises:
            APIError: If authentication fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        if reauth:
            logger.info("Re-authenticating account %d", credentials.account_id)
        else:
            logger.info("Authenticating account %d", credentials.account_id)

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

        # Store credentials for refresh monitoring
        self._accounts[credentials.account_id] = credentials
        logger.info("Account %d authenticated successfully", credentials.account_id)

        # Notify callback
        if self._on_account_ready is not None:
            try:
                await self._on_account_ready(credentials.account_id, reconnect, reauth)
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
        logger.info("Authenticating by trader login %d", trader_login)

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
            logger.info("Account %d removed from auth manager", account_id)
            return True
        return False

    async def start(self) -> None:
        """Start the token refresh monitor.

        This runs a background task that periodically checks for expiring
        tokens and refreshes them automatically.
        """
        if self._running:
            return

        self._running = True
        self._task_group = anyio.create_task_group()
        await self._task_group.__aenter__()
        self._task_group.start_soon(self._refresh_loop)
        logger.debug("Token refresh monitor started")

    async def stop(self) -> None:
        """Stop the token refresh monitor."""
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

        logger.debug("Token refresh monitor stopped")

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
                        logger.info(
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

                    logger.info(
                        "Token refreshed for account %d, new expiry in %ds",
                        account_id,
                        response.expires_in,
                    )

                    # Re-authenticate the account with the new token
                    await self.authenticate_account(new_credentials, reauth=True)

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
