"""Authentication layer for cTrader API.

This module provides application and account authentication,
with automatic token refresh management.
"""

from .credentials import AccountCredentials
from .manager import AuthManager
from .trigger import AuthTrigger


__all__ = [
    "AccountCredentials",
    "AuthManager",
    "AuthTrigger",
]
