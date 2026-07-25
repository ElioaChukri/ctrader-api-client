from __future__ import annotations

from enum import Enum


class AuthTrigger(Enum):
    """Reason an account authentication was performed.

    Threaded through account authentication so downstream logic can
    distinguish cases where the server-side session (and its subscriptions)
    is lost from cases where it is preserved.
    """

    INITIAL = "INITIAL"
    RECONNECT = "RECONNECT"
    TOKEN_REFRESH = "TOKEN_REFRESH"
    ACCOUNT_REAUTH = "ACCOUNT_REAUTH"
