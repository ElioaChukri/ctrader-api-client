"""Per-account session state.

An account the manager knows about is always in exactly one of three
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
