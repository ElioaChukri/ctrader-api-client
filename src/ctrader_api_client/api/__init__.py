"""Domain-specific API classes for cTrader operations.

This module provides namespaced APIs for different aspects of trading:
- AccountsAPI: Account information retrieval
- SymbolsAPI: Symbol lookup and search
- TradingAPI: Order placement and position management
- MarketDataAPI: Market data subscriptions and historical data
"""

from .accounts import AccountsAPI
from .market_data import MarketDataAPI
from .symbols import SymbolsAPI
from .trading import TradingAPI


__all__ = [
    "AccountsAPI",
    "MarketDataAPI",
    "SymbolsAPI",
    "TradingAPI",
]
