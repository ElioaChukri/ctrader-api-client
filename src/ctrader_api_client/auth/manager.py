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

from .._internal import Clock, MonotonicClock
from .._internal.proto import (
    ProtoOAAccountAuthReq,
    ProtoOAAccountAuthRes,
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAErrorCode,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAGetAccountListByAccessTokenRes,
    ProtoOARefreshTokenReq,
    ProtoOARefreshTokenRes,
)
from ..exceptions import (
    AccountAuthError,
    AccountNotFoundError,
    APIError,
    ApplicationAuthError,
    TokenExpiredError,
    TokenRefreshError,
)
from ..models import AccountSummary
from ._session import Authorized, AwaitingRecovery, TrackedAccount
from .credentials import AccountCredentials
from .policy import ReauthPolicy, RefreshPolicy
from .trigger import AuthTrigger


if TYPE_CHECKING:
    from ..connection.protocol import Protocol


logger = logging.getLogger(__name__)

TokenRefreshCallback = Callable[[AccountCredentials], Awaitable[None]]
AccountReadyCallback = Callable[[int, AuthTrigger], Awaitable[None]]  # (account_id, trigger)

# Codes the server uses when the token itself is the problem, rather than the
# application, the account or the request.
_TOKEN_ERROR_CODES = frozenset(
    {
        ProtoOAErrorCode.OA_AUTH_TOKEN_EXPIRED.name,
        ProtoOAErrorCode.CH_ACCESS_TOKEN_INVALID.name,
    }
)


def _is_token_failure(error: APIError) -> bool:
    """Whether the failure means the token must be replaced rather than retried."""
    return error.error_code in _TOKEN_ERROR_CODES


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
        refresh_policy: RefreshPolicy | None = None,
        reauth_policy: ReauthPolicy | None = None,
        clock: Clock | None = None,
        on_tokens_refreshed: TokenRefreshCallback | None = None,
        on_account_ready: AccountReadyCallback | None = None,
    ) -> None:
        """Initialize the authentication manager.

        Args:
            protocol: The protocol instance for sending auth requests.
            client_id: OAuth client ID for the application.
            client_secret: OAuth client secret for the application.
            refresh_policy: When to refresh access tokens and how hard to try.
            reauth_policy: Backoff for re-establishing sessions the server dropped.
            clock: Time source for the refresh check interval and recovery backoff.
            on_tokens_refreshed: Async callback invoked when tokens are refreshed.
                Receives the new AccountCredentials. Use this to persist tokens.
            on_account_ready: Async callback invoked when an account is authenticated.
                Receives (account_id, trigger). Use this to perform any initial client setup.
        """
        self._protocol = protocol
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh = refresh_policy if refresh_policy is not None else RefreshPolicy()
        self._reauth = reauth_policy if reauth_policy is not None else ReauthPolicy()
        self._clock = clock if clock is not None else MonotonicClock()
        self._on_tokens_refreshed = on_tokens_refreshed
        self._on_account_ready = on_account_ready

        # Every account the manager knows about, keyed by cTID trader account
        # ID, each carrying its own session state.
        self._sessions: dict[int, TrackedAccount] = {}

        # Wakes the recovery monitor when an account needs re-authenticating
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
        return list(self._sessions.keys())

    @property
    def authorized_accounts(self) -> list[int]:
        """List of account IDs with a live, authorized server-side session."""
        return [account_id for account_id, tracked in self._sessions.items() if isinstance(tracked.session, Authorized)]

    def is_account_authorized(self, account_id: int) -> bool:
        """Whether the account currently has a live, authorized session.

        Returns False after a server-side account disconnect, or after the
        connection drops, until re-authentication succeeds.

        Args:
            account_id: The cTID trader account ID.
        """
        tracked = self._sessions.get(account_id)
        return tracked is not None and isinstance(tracked.session, Authorized)

    def get_credentials(self, account_id: int) -> AccountCredentials | None:
        """Get credentials for an account.

        Args:
            account_id: The cTID trader account ID.

        Returns:
            The account credentials, or None if not authenticated.
        """
        tracked = self._sessions.get(account_id)
        return tracked.credentials if tracked is not None else None

    def all_credentials(self) -> list[AccountCredentials]:
        """Credentials for every account the manager holds, oldest first.

        Returns:
            A snapshot list, safe to iterate while accounts are added or removed.
        """
        return [tracked.credentials for tracked in self._sessions.values()]

    async def authenticate_app(self, timeout: float = 30.0) -> ProtoOAApplicationAuthRes:
        """Authenticate the application with cTrader.

        This must be called before authenticating any accounts.

        Args:
            timeout: Request timeout in seconds.

        Returns:
            The authentication response from the server.

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
            response = await self._protocol.request(request, ProtoOAApplicationAuthRes, timeout=timeout)
        except APIError as e:
            raise ApplicationAuthError(e.error_code, e.description) from e

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
            response = await self._protocol.request(request, ProtoOAAccountAuthRes, timeout=timeout)
        except APIError as e:
            if _is_token_failure(e):
                raise TokenExpiredError(credentials.account_id) from e
            raise AccountAuthError(e.error_code, e.description, credentials.account_id) from e

        # Store credentials for refresh monitoring and mark the session live
        self._sessions[credentials.account_id] = TrackedAccount(credentials, Authorized())
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
            TokenExpiredError: If the server rejects the access token.
            APIError: If the request fails for any other reason.
            CTraderConnectionTimeoutError: If request times out.
        """
        logger.debug("Fetching accounts for access token")

        request = ProtoOAGetAccountListByAccessTokenReq(
            access_token=access_token,
        )

        try:
            response = await self._protocol.request(
                request,
                ProtoOAGetAccountListByAccessTokenRes,
                timeout=timeout,
            )
        except APIError as e:
            if _is_token_failure(e):
                raise TokenExpiredError from e
            raise

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
            TokenExpiredError: If the server rejects the access token.
            AccountAuthError: If the server rejects the account.
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
        if account_id in self._sessions:
            del self._sessions[account_id]
            logger.debug("Account %d removed from auth manager", account_id)
            return True
        return False

    def handle_connection_lost(self) -> None:
        """Forget every server-side session because the transport dropped.

        Credentials survive a dropped link; the sessions they established do
        not. Nothing is scheduled for recovery here — re-authentication of the
        whole client is driven by the reconnect handler once the link is back.
        """
        self._sessions = {
            account_id: TrackedAccount(tracked.credentials) for account_id, tracked in self._sessions.items()
        }

    def handle_account_disconnect(self, account_id: int) -> None:
        """Handle a server-side account disconnect.

        Marks the account's session as no longer authorized and schedules
        recovery re-authentication on the existing connection. Idempotent while
        a recovery is already pending for the account.

        Args:
            account_id: The cTID trader account ID reported as disconnected.
        """
        tracked = self._sessions.get(account_id)
        if tracked is None or isinstance(tracked.session, AwaitingRecovery):
            return

        self._sessions[account_id] = TrackedAccount(tracked.credentials, AwaitingRecovery())
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
            except Exception as e:
                logger.warning("Auth monitors did not shut down cleanly: %s", e)
            self._task_group = None

        self.handle_connection_lost()

        logger.debug("Auth monitors stopped")

    def _recovery_queue(self) -> list[tuple[int, AccountCredentials, AwaitingRecovery]]:
        """Accounts awaiting recovery, each with its credentials and retry state."""
        queue: list[tuple[int, AccountCredentials, AwaitingRecovery]] = []
        for account_id, tracked in self._sessions.items():
            if isinstance(tracked.session, AwaitingRecovery):
                queue.append((account_id, tracked.credentials, tracked.session))
        return queue

    def _defer_recovery(self, account_id: int) -> None:
        """Back off before the next recovery attempt for a single account."""
        tracked = self._sessions.get(account_id)
        if tracked is None or not isinstance(tracked.session, AwaitingRecovery):
            return

        attempts = tracked.session.attempts + 1
        delay = min(self._reauth.min_wait * 2 ** (attempts - 1), self._reauth.max_wait)
        self._sessions[account_id] = TrackedAccount(
            tracked.credentials,
            AwaitingRecovery(attempts=attempts, next_attempt_at=self._clock.now() + delay),
        )

    async def _wait_for_retry(self, delay: float, flagged: anyio.Event) -> None:
        """Wait out a backoff, returning early if another account needs recovery.

        Without the early return, an account already deep into its backoff
        would hold up an account dropped moments ago, which is exactly the
        coupling per-account backoff exists to avoid.
        """
        async with anyio.create_task_group() as task_group:

            async def until_due() -> None:
                await self._clock.sleep(delay)
                task_group.cancel_scope.cancel()

            async def until_flagged() -> None:
                await flagged.wait()
                task_group.cancel_scope.cancel()

            task_group.start_soon(until_due)
            task_group.start_soon(until_flagged)

    async def _reauth_loop(self) -> None:
        """Recover accounts dropped by a server-side account disconnect.

        Waits for accounts flagged by handle_account_disconnect, then
        re-authenticates them on the existing connection. Each account backs off
        on its own schedule, so one that keeps failing cannot hold up another,
        and retries continue until every account succeeds, is removed, or the
        manager stops. A successful re-auth restores authorized state and emits
        a ReadyEvent so subscriptions can be restored.
        """
        while self._running:
            # Consume any pending notification before reading the queue, so a
            # disconnect reported after this point still wakes the next wait.
            if self._reauth_signal.is_set():
                self._reauth_signal = anyio.Event()
            flagged = self._reauth_signal

            queue = self._recovery_queue()
            if not queue:
                await flagged.wait()
                continue

            now = self._clock.now()
            due = [
                (account_id, credentials) for account_id, credentials, state in queue if state.next_attempt_at <= now
            ]

            if not due:
                soonest = min(state.next_attempt_at for _, _, state in queue)
                await self._wait_for_retry(soonest - now, flagged)
                continue

            for account_id, credentials in due:
                try:
                    await self.authenticate_account(credentials, trigger=AuthTrigger.ACCOUNT_REAUTH)
                except Exception as e:
                    logger.warning(
                        "Recovery re-authentication for account %d failed, will retry: %s",
                        account_id,
                        e,
                    )
                    self._defer_recovery(account_id)

    async def _refresh_loop(self) -> None:
        """Periodically check and refresh expiring tokens."""
        with anyio.CancelScope() as scope:
            self._task_scope = scope
            while self._running:
                await self._clock.sleep(self._refresh.check_interval)

                for account_id, tracked in list(self._sessions.items()):
                    credentials = tracked.credentials

                    if credentials.expires_soon(self._refresh.buffer_seconds):
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
        tracked = self._sessions.get(account_id)
        if tracked is None:
            return

        credentials = tracked.credentials
        last_error: Exception | None = None

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._refresh.retry_attempts),
                wait=wait_exponential(
                    min=self._refresh.retry_min_wait,
                    max=self._refresh.retry_max_wait,
                ),
                retry=retry_if_exception_type(APIError),
                reraise=True,
            ):
                with attempt:
                    logger.debug(
                        "Token refresh attempt %d/%d for account %d",
                        attempt.retry_state.attempt_number,
                        self._refresh.retry_attempts,
                        account_id,
                    )

                    # Send refresh request
                    request = ProtoOARefreshTokenReq(
                        refresh_token=credentials.refresh_token,
                    )
                    try:
                        response = await self._protocol.request(request, ProtoOARefreshTokenRes)
                    except APIError as e:
                        # A dead refresh token cannot be retried back to life.
                        if _is_token_failure(e):
                            raise TokenExpiredError(account_id) from e
                        raise

                    # Update credentials, leaving the session state untouched
                    new_credentials = credentials.with_refreshed_tokens(
                        access_token=response.access_token,
                        refresh_token=response.refresh_token,
                        expires_in=response.expires_in,
                    )
                    current = self._sessions.get(account_id)
                    self._sessions[account_id] = TrackedAccount(
                        new_credentials,
                        current.session if current is not None else None,
                    )

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
