"""Authentication layer for cTrader API.

This module provides application and account authentication,
with automatic token refresh management.
"""

from ctrader_api_client.auth.credentials import AccountCredentials
from ctrader_api_client.auth.manager import AuthManager


__all__ = [
    "AccountCredentials",
    "AuthManager",
]
