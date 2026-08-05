"""Authentication layer for cTrader API.

Sessions are established by the manager, kept ahead of token expiry by the
refresher, and put back by the recovery monitor; all three share one store of
accounts and session state.
"""

from ._recovery import SessionRecovery
from ._refresh import TokenRefresher
from ._session import SessionStore
from .credentials import AccountCredentials
from .manager import AuthManager
from .policy import ReauthPolicy, RefreshPolicy
from .store import TokenStore


__all__ = [
    "AccountCredentials",
    "AuthManager",
    "ReauthPolicy",
    "RefreshPolicy",
    "SessionRecovery",
    "SessionStore",
    "TokenRefresher",
    "TokenStore",
]
