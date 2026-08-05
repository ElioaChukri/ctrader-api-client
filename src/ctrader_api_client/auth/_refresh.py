"""Keeping access tokens ahead of their expiry.

Rotating a token is a separate concern from establishing a session with it:
the refresher watches the clock, the manager does the authenticating.
"""

from __future__ import annotations

import logging
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
from .._internal.proto import ProtoOARefreshTokenReq, ProtoOARefreshTokenRes
from ..enums import AuthTrigger
from ..events import EventPublisher, TokenRefreshFailedEvent
from ..exceptions import APIError, TokenExpiredError, TokenRefreshError
from ._session import SessionAuthenticator, SessionStore
from .policy import RefreshPolicy
from .store import TokenStore


if TYPE_CHECKING:
    from ..connection.protocol import Protocol


logger = logging.getLogger(__name__)


class TokenRefresher:
    """Refreshes access tokens before they expire, and re-authorizes with them.

    A refresh that exhausts its retries keeps the existing credentials and
    reports a `TokenRefreshFailedEvent`; the monitor stays alive so the next
    check interval can recover from a transient outage.
    """

    def __init__(
        self,
        protocol: Protocol,
        store: SessionStore,
        authenticator: SessionAuthenticator,
        publisher: EventPublisher,
        policy: RefreshPolicy | None = None,
        clock: Clock | None = None,
        token_store: TokenStore | None = None,
    ) -> None:
        """Initialize the token refresh monitor.

        Args:
            protocol: The protocol instance for sending refresh requests.
            store: Where the accounts and their credentials are kept.
            authenticator: Re-authorizes the account with its rotated token.
            publisher: Where TokenRefreshFailedEvent is published.
            policy: When to refresh access tokens and how hard to try.
            clock: Time source for the refresh check interval.
            token_store: Durable storage for rotated credentials. Without one,
                refreshed tokens live only in memory and are lost on restart.
        """
        self._protocol = protocol
        self._store = store
        self._authenticator = authenticator
        self._publisher = publisher
        self._policy = policy if policy is not None else RefreshPolicy()
        self._clock = clock if clock is not None else MonotonicClock()
        self._token_store = token_store

        self._task_scope: anyio.CancelScope | None = None
        self._running = False

    async def serve(self, *, task_status: anyio.abc.TaskStatus[None] = anyio.TASK_STATUS_IGNORED) -> None:
        """Refresh expiring tokens until stopped or cancelled.

        Raises:
            RuntimeError: If the monitor is already being served.
        """
        if self._running:
            raise RuntimeError("Token refresh monitor is already running")

        self._running = True
        logger.debug("Token refresh monitor started")
        try:
            with anyio.CancelScope() as scope:
                self._task_scope = scope
                task_status.started()
                await self._refresh_loop()
        finally:
            self._running = False
            self._task_scope = None
            logger.debug("Token refresh monitor stopped")

    async def stop(self) -> None:
        """Ask the monitor to wind down."""
        self._running = False

        if self._task_scope is not None:
            self._task_scope.cancel()

    async def _refresh_loop(self) -> None:
        """Periodically check and refresh expiring tokens."""
        while self._running:
            await self._clock.sleep(self._policy.check_interval)

            for account_id, credentials in self._store.items():
                if credentials.expires_soon(self._policy.buffer_seconds):
                    logger.debug(
                        "Token for account %d expires soon (%.0fs remaining), refreshing",
                        account_id,
                        credentials.time_until_expiry(),
                    )
                    try:
                        await self._refresh_account(account_id)
                    except TokenRefreshError as e:
                        logger.error(
                            "Failed to refresh token for account %d, will retry in %.0fs: %s",
                            account_id,
                            self._policy.check_interval,
                            e,
                        )
                        await self._publisher.emit(TokenRefreshFailedEvent(account_id=account_id, error=e))

    async def _refresh_account(self, account_id: int) -> None:
        """Refresh tokens for an account with retry logic.

        Args:
            account_id: The cTID trader account ID.

        Raises:
            TokenRefreshError: If refresh fails after all retries.
        """
        credentials = self._store.credentials(account_id)
        if credentials is None:
            return

        last_error: Exception | None = None

        # Held from before the request goes out until the account is authorized
        # again, because the disconnect the server reports for the old token
        # arrives inside that window and means nothing about the session.
        self._store.begin_refresh(account_id)

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._policy.retry_attempts),
                wait=wait_exponential(
                    min=self._policy.retry_min_wait,
                    max=self._policy.retry_max_wait,
                ),
                retry=retry_if_exception_type(APIError),
                reraise=True,
            ):
                with attempt:
                    logger.debug(
                        "Token refresh attempt %d/%d for account %d",
                        attempt.retry_state.attempt_number,
                        self._policy.retry_attempts,
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
                        if e.is_token_failure():
                            raise TokenExpiredError(account_id) from e
                        raise

                    # Update credentials, leaving the session state untouched.
                    # The server has already invalidated the old pair, so the
                    # new one is kept even if persisting it below fails.
                    new_credentials = credentials.with_refreshed_tokens(
                        access_token=response.access_token,
                        refresh_token=response.refresh_token,
                        expires_in=response.expires_in,
                    )
                    self._store.replace_credentials(new_credentials)

                    if self._token_store is not None:
                        await self._token_store.save(new_credentials)

                    logger.debug(
                        "Token refreshed for account %d, new expiry in %ds",
                        account_id,
                        response.expires_in,
                    )

                    # Re-authenticate the account with the new token
                    await self._authenticator.establish(new_credentials, AuthTrigger.TOKEN_REFRESH)

        except APIError as e:
            last_error = e
        except Exception as e:
            last_error = e
        finally:
            self._store.end_refresh(account_id)

        if last_error is not None:
            raise TokenRefreshError(account_id, last_error)
