from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class AccountCredentials:
    """Stores authentication credentials for a trading account.

    Attributes:
        account_id: The cTID trader account ID.
        access_token: OAuth access token for API authentication.
        refresh_token: OAuth refresh token for obtaining new access tokens.
        expires_at: Unix epoch timestamp when the access token expires.
    """

    account_id: int
    access_token: str
    refresh_token: str
    expires_at: float

    def expires_soon(self, buffer_seconds: float = 300.0) -> bool:
        """Check if the access token expires within the buffer period.

        Args:
            buffer_seconds: Number of seconds before expiry to consider "soon".
                Defaults to 300 (5 minutes).

        Returns:
            True if the token expires within buffer_seconds from now.
        """
        return time.time() >= (self.expires_at - buffer_seconds)

    def is_expired(self) -> bool:
        """Check if the access token has already expired.

        Returns:
            True if the token has expired.
        """
        return time.time() >= self.expires_at

    def time_until_expiry(self) -> float:
        """Get seconds remaining until token expires.

        Returns:
            Seconds until expiry. Negative if already expired.
        """
        return self.expires_at - time.time()

    def with_refreshed_tokens(
        self,
        access_token: str,
        refresh_token: str,
        expires_in: int,
    ) -> AccountCredentials:
        """Create a new instance with refreshed tokens.

        Args:
            access_token: The new access token.
            refresh_token: The new refresh token.
            expires_in: Seconds until the new access token expires.

        Returns:
            A new AccountCredentials instance with updated tokens.
        """
        return AccountCredentials(
            account_id=self.account_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=time.time() + expires_in,
        )
