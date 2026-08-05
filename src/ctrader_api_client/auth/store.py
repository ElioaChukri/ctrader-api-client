"""Durable storage abstraction for rotated account credentials."""

from __future__ import annotations

from typing import Protocol as TypingProtocol

from .credentials import AccountCredentials


class TokenStore(TypingProtocol):
    """Durable storage the client writes rotated credentials through.

    cTrader rotates both the access token and the refresh token on every
    refresh, and invalidates the old pair immediately. A process that restarts
    holding the pair it was originally given can no longer authenticate, so the
    replacement must be persisted as it is issued rather than read back at
    shutdown.

    Write-only by design. Reading the stored pair back at startup and passing it
    to `authenticate_trader` is the caller's job, since only the caller knows
    which accounts a given process is responsible for.
    """

    async def save(self, credentials: AccountCredentials) -> None:
        """Persist the credentials for an account, replacing any earlier pair.

        Called during token refresh, before the new access token is used. A
        save that raises aborts the refresh, which is reported as a
        TokenRefreshFailedEvent and retried on the next check interval, so a
        transient storage outage recovers on its own.

        Args:
            credentials: The freshly issued tokens and their expiry.
        """
        ...
