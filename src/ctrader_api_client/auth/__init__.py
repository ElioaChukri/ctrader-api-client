"""Authentication layer for cTrader API.

This module provides application and account authentication,
with automatic token refresh management.
"""

from .credentials import AccountCredentials
from .manager import AuthManager


__all__ = [
    "AccountCredentials",
    "AuthManager",
]
