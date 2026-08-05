"""Putting sessions back after the server, or the link, takes them away.

Two things can end a session that the credentials behind it would still
support: the server disconnecting a single account, and the connection
dropping altogether. Both are recovered here, on their own schedules.
"""

from __future__ import annotations

import logging

import anyio
import anyio.abc

from .._internal import Clock, MonotonicClock
from ..enums import AuthTrigger
from ..events import AccountDisconnectEvent, EventPublisher, ReadyEvent, ReconnectedEvent
from ..exceptions import AccountAuthError
from ._session import AwaitingRecovery, SessionAuthenticator, SessionStore
from .policy import ReauthPolicy


logger = logging.getLogger(__name__)


class SessionRecovery:
    """Re-establishes sessions the server or the transport took away.

    Serves as the connection supervisor's listener, and as the event router's
    handler for server-side account disconnects.
    """

    def __init__(
        self,
        store: SessionStore,
        authenticator: SessionAuthenticator,
        publisher: EventPublisher,
        policy: ReauthPolicy | None = None,
        clock: Clock | None = None,
    ) -> None:
        """Initialize the session recovery monitor.

        Args:
            store: Where the accounts and their session state are kept.
            authenticator: Re-authorizes the application and the accounts.
            publisher: Where ReconnectedEvent is published.
            policy: Backoff for re-establishing sessions the server dropped.
            clock: Time source for the recovery backoff.
        """
        self._store = store
        self._authenticator = authenticator
        self._publisher = publisher
        self._policy = policy if policy is not None else ReauthPolicy()
        self._clock = clock if clock is not None else MonotonicClock()

        # Wakes the recovery monitor when an account needs re-authenticating
        self._reauth_signal = anyio.Event()

        # Accounts whose reported disconnect is still being checked, so a
        # repeated report does not start a second check against the server.
        self._verifying: set[int] = set()

        self._task_scope: anyio.CancelScope | None = None
        self._running = False

    async def serve(self, *, task_status: anyio.abc.TaskStatus[None] = anyio.TASK_STATUS_IGNORED) -> None:
        """Recover dropped account sessions until stopped or cancelled.

        Sessions are discarded as this returns, since they live on the far side
        of a link that is going away.

        Raises:
            RuntimeError: If the monitor is already being served.
        """
        if self._running:
            raise RuntimeError("Session recovery monitor is already running")

        self._running = True
        logger.debug("Session recovery monitor started")
        try:
            with anyio.CancelScope() as scope:
                self._task_scope = scope
                task_status.started()
                await self._reauth_loop()
        finally:
            self._running = False
            self._task_scope = None
            self._store.invalidate_all()
            logger.debug("Session recovery monitor stopped")

    async def stop(self) -> None:
        """Ask the monitor to wind down."""
        self._running = False

        if self._task_scope is not None:
            self._task_scope.cancel()

    async def handle_account_disconnect(self, account_id: int) -> None:
        """Establish whether a reported account disconnect actually happened.

        The server reports a disconnect whenever the token behind an
        authorization is rotated, even though the session on this channel is
        untouched. Taking the report at face value would mark a working account
        unauthorized and publish a drop that never occurred, so the report is
        checked against the server before anything acts on it.

        Every report the server sends for a token rotation arrives while the
        client is replacing that authorization, and for the length of that
        replacement the account really is unauthorized: it answers nothing, and
        asking it anything would only confirm a state the client is already
        undoing. So the check waits for the refresh to settle before it asks.
        The refresh always starts before the report it provokes, so there is no
        ordering in which the report escapes the wait.

        The check itself asks whether the account is still served on this link
        rather than trying to re-authorize it, since re-authorizing answers for
        the token as much as for the session.

        A check that cannot be completed is not an answer of no. The account is
        left as it was, because nothing has said the session ended.

        Args:
            account_id: The cTID trader account ID reported as disconnected.
        """
        if self._store.is_refreshing(account_id):
            logger.debug(
                "Account %d was reported as disconnected while its token was being "
                "refreshed; waiting for that to settle before checking",
                account_id,
            )
            await self._store.wait_for_refresh(account_id)

        credentials = self._store.credentials(account_id)
        if credentials is None or not self._store.is_authorized(account_id):
            return

        if account_id in self._verifying:
            return

        self._verifying.add(account_id)
        try:
            try:
                alive = await self._authenticator.probe_session(account_id)
            except Exception as e:
                logger.debug(
                    "Could not check the disconnect reported for account %d, leaving it as it is: %s",
                    account_id,
                    e,
                )
                return

            if alive:
                logger.debug(
                    "Account %d reported as disconnected still holds its session; ignoring",
                    account_id,
                )
                return

            await self._report_dropped(account_id)
        finally:
            self._verifying.discard(account_id)

    async def _report_dropped(self, account_id: int) -> None:
        """Publish a confirmed drop and arm recovery for it.

        Reached once the server has stopped serving the account on this link, so
        the session is genuinely gone.
        """
        logger.warning(
            "Account %d disconnected by server; scheduling re-authentication",
            account_id,
        )
        self._store.flag_for_recovery(account_id)
        self._reauth_signal.set()
        await self._publisher.emit(AccountDisconnectEvent(account_id=account_id))

    async def on_connection_lost(self) -> None:
        """Discard the sessions that died with the link.

        Keeps `is_account_authorized` honest while the client is offline. The
        credentials are kept, so the sessions can be re-established once the
        link is back.
        """
        self._store.invalidate_all()

    async def on_connection_restored(self) -> None:
        """Re-authenticate the application and every account on the new link.

        Reports the outcome as a `ReconnectedEvent` rather than raising: the
        link is already back, and a caller can only act on a failure it is told
        about. Without application authentication nothing else can be
        attempted, so that failure is reported on its own.
        """
        logger.debug("Connection restored, re-authenticating...")

        try:
            await self._authenticator.authenticate_app()
            logger.debug("App re-authenticated successfully")
        except Exception as e:
            logger.error("Failed to re-authenticate app after reconnect: %s", e)
            await self._publisher.emit(
                ReconnectedEvent(
                    app_auth_restored=False,
                    restored_accounts=(),
                    failed_accounts=(),
                )
            )
            return

        restored: list[int] = []
        failed: list[tuple[int, str]] = []

        for credentials in self._store.all_credentials():
            account_id = credentials.account_id
            try:
                await self._authenticator.establish(credentials, AuthTrigger.RECONNECT)
                restored.append(account_id)
                logger.debug("Re-authenticated account %d", account_id)
            except Exception as e:
                logger.error("Failed to re-authenticate account %d: %s", account_id, e)
                failed.append((account_id, str(e)))

        await self._publisher.emit(
            ReconnectedEvent(
                app_auth_restored=True,
                restored_accounts=tuple(restored),
                failed_accounts=tuple(failed),
            )
        )

    def _defer_recovery(self, account_id: int, state: AwaitingRecovery) -> None:
        """Back off before the next recovery attempt for a single account."""
        attempts = state.attempts + 1
        delay = min(self._policy.min_wait * 2 ** (attempts - 1), self._policy.max_wait)
        self._store.reschedule_recovery(
            account_id,
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
        monitor stops. A successful re-auth restores authorized state and emits
        a ReadyEvent so subscriptions can be restored.
        """
        while self._running:
            # Consume any pending notification before reading the queue, so a
            # disconnect reported after this point still wakes the next wait.
            if self._reauth_signal.is_set():
                self._reauth_signal = anyio.Event()
            flagged = self._reauth_signal

            queue = self._store.awaiting_recovery()
            if not queue:
                await flagged.wait()
                continue

            now = self._clock.now()
            due = [
                (account_id, credentials, state)
                for account_id, credentials, state in queue
                if state.next_attempt_at <= now
            ]

            if not due:
                soonest = min(state.next_attempt_at for _, _, state in queue)
                await self._wait_for_retry(soonest - now, flagged)
                continue

            for account_id, credentials, state in due:
                try:
                    await self._authenticator.establish(credentials, AuthTrigger.ACCOUNT_REAUTH)
                except AccountAuthError as e:
                    if not e.is_already_authorized():
                        logger.warning(
                            "Recovery re-authentication for account %d failed, will retry: %s",
                            account_id,
                            e,
                        )
                        self._defer_recovery(account_id, state)
                        continue
                    # The session came back by some other route between
                    # attempts. Retrying could only be refused the same way, so
                    # take the account as recovered and announce it, noting that
                    # nothing re-applied the subscriptions the dead session took
                    # with it.
                    logger.warning(
                        "Account %d holds a session again; its subscriptions were not re-applied",
                        account_id,
                    )
                    self._store.authorize(credentials)
                    await self._publisher.emit(ReadyEvent(account_id=account_id, trigger=AuthTrigger.ACCOUNT_REAUTH))
                except Exception as e:
                    logger.warning(
                        "Recovery re-authentication for account %d failed, will retry: %s",
                        account_id,
                        e,
                    )
                    self._defer_recovery(account_id, state)
