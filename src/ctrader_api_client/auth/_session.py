"""Per-account session state, and where it is kept.

An account the client knows about is always in exactly one of three
situations, and keeping them in the type system rather than in parallel sets
means they cannot drift apart:

- credentials are held but there is no server-side session (``session is None``)
- the session is live and authorized (:class:`Authorized`)
- the server dropped the session and recovery is in flight
  (:class:`AwaitingRecovery`)

These types are internal to the auth package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol as TypingProtocol

import anyio

from ..enums import AuthTrigger
from .credentials import AccountCredentials


@dataclass(frozen=True, slots=True)
class Authorized:
    """The account has a live, authorized session on the current connection."""


@dataclass(frozen=True, slots=True)
class AwaitingRecovery:
    """The server dropped the account's session; re-authentication is pending.

    The backoff is held per account so that one account that keeps failing
    cannot delay the recovery of another.

    Attributes:
        attempts: How many recovery attempts have already failed.
        next_attempt_at: Clock reading before which no further attempt is made.
            Defaults to 0.0 so a freshly dropped session is retried at once.
    """

    attempts: int = 0
    next_attempt_at: float = 0.0


type Session = Authorized | AwaitingRecovery


@dataclass(frozen=True, slots=True)
class TrackedAccount:
    """Credentials the manager holds, together with their session state.

    Attributes:
        credentials: The tokens used to authenticate the account.
        session: The server-side session, or None when there is none. Absence
            covers both a never-authenticated account and one whose session
            died with the connection.
    """

    credentials: AccountCredentials
    session: Session | None = None


class SessionAuthenticator(TypingProtocol):
    """Whatever turns credentials into live sessions on the current link."""

    async def authenticate_app(self, timeout: float = 30.0) -> None:
        """Authenticate the application, without which no account can be."""
        ...

    async def establish(
        self,
        credentials: AccountCredentials,
        trigger: AuthTrigger,
        timeout: float = 30.0,
    ) -> None:
        """Authorize an account, recording why so the right events follow."""
        ...

    async def probe_session(self, account_id: int, timeout: float = 10.0) -> bool:
        """Whether the account still holds a live session on this link.

        Raises whatever stopped the question from being answered — including a
        refusal that is about the token rather than the session — which is not
        the same as an answer of no.
        """
        ...


class SessionStore:
    """Every account the client knows about, keyed by cTID trader account ID.

    Credentials outlive the sessions they establish: a dropped link or a
    server-side account disconnect invalidates the session while the tokens
    stay valid. Holding both in one place is what keeps that distinction from
    being re-derived, differently, by each of the things that care about it.
    """

    def __init__(self) -> None:
        self._accounts: dict[int, TrackedAccount] = {}

        # Accounts whose authorization is being replaced by a token refresh.
        # The server drops the old authorization as it issues the new pair, so
        # for that stretch the account is genuinely unauthorized and answers
        # nothing — a state no observer should mistake for a lost session.
        self._refreshing: dict[int, anyio.Event] = {}

    def begin_refresh(self, account_id: int) -> None:
        """Note that the account's authorization is being replaced."""
        if account_id not in self._refreshing:
            self._refreshing[account_id] = anyio.Event()

    def end_refresh(self, account_id: int) -> None:
        """Note that it has been replaced, or that the attempt gave up."""
        settled = self._refreshing.pop(account_id, None)
        if settled is not None:
            settled.set()

    def is_refreshing(self, account_id: int) -> bool:
        """Whether a refresh is currently replacing the account's authorization."""
        return account_id in self._refreshing

    async def wait_for_refresh(self, account_id: int) -> None:
        """Wait until no refresh is replacing the account's authorization."""
        settled = self._refreshing.get(account_id)
        if settled is not None:
            await settled.wait()

    def account_ids(self) -> list[int]:
        """Every account held, oldest first."""
        return list(self._accounts)

    def authorized_ids(self) -> list[int]:
        """Every account with a live, authorized session, oldest first."""
        return [account_id for account_id, tracked in self._accounts.items() if isinstance(tracked.session, Authorized)]

    def is_authorized(self, account_id: int) -> bool:
        """Whether the account has a live, authorized session."""
        tracked = self._accounts.get(account_id)
        return tracked is not None and isinstance(tracked.session, Authorized)

    def credentials(self, account_id: int) -> AccountCredentials | None:
        """The account's current credentials, or None if it is not held."""
        tracked = self._accounts.get(account_id)
        return tracked.credentials if tracked is not None else None

    def all_credentials(self) -> list[AccountCredentials]:
        """Credentials for every account held, oldest first.

        A snapshot, safe to iterate while accounts are added or removed.
        """
        return [tracked.credentials for tracked in self._accounts.values()]

    def items(self) -> list[tuple[int, AccountCredentials]]:
        """Every account and its credentials, as a snapshot."""
        return [(account_id, tracked.credentials) for account_id, tracked in self._accounts.items()]

    def authorize(self, credentials: AccountCredentials) -> None:
        """Record the account as holding a live session on the current link."""
        self._accounts[credentials.account_id] = TrackedAccount(credentials, Authorized())

    def replace_credentials(self, credentials: AccountCredentials) -> None:
        """Swap in rotated tokens, leaving the session state as it was."""
        current = self._accounts.get(credentials.account_id)
        self._accounts[credentials.account_id] = TrackedAccount(
            credentials,
            current.session if current is not None else None,
        )

    def remove(self, account_id: int) -> bool:
        """Forget the account entirely. Returns whether it was held."""
        return self._accounts.pop(account_id, None) is not None

    def invalidate_all(self) -> None:
        """Forget every server-side session, keeping the credentials.

        For a dropped link: the sessions lived on the far side of it, the
        tokens did not.
        """
        self._accounts = {
            account_id: TrackedAccount(tracked.credentials) for account_id, tracked in self._accounts.items()
        }

    def flag_for_recovery(self, account_id: int) -> bool:
        """Mark a session the server dropped as needing re-authentication.

        Returns:
            True if this newly flagged the account, False if it is not held or
            a recovery is already pending for it.
        """
        tracked = self._accounts.get(account_id)
        if tracked is None or isinstance(tracked.session, AwaitingRecovery):
            return False

        self._accounts[account_id] = TrackedAccount(tracked.credentials, AwaitingRecovery())
        return True

    def reschedule_recovery(self, account_id: int, state: AwaitingRecovery) -> None:
        """Record the next attempt for an account still awaiting recovery.

        Ignored if the account was removed or recovered in the meantime, so a
        late failure cannot resurrect a session that is no longer pending.
        """
        tracked = self._accounts.get(account_id)
        if tracked is None or not isinstance(tracked.session, AwaitingRecovery):
            return

        self._accounts[account_id] = TrackedAccount(tracked.credentials, state)

    def awaiting_recovery(self) -> list[tuple[int, AccountCredentials, AwaitingRecovery]]:
        """Accounts awaiting recovery, each with its credentials and retry state."""
        return [
            (account_id, tracked.credentials, tracked.session)
            for account_id, tracked in self._accounts.items()
            if isinstance(tracked.session, AwaitingRecovery)
        ]
