"""High-level Pydantic models for cTrader API.

This module provides Pythonic wrappers over raw protobuf types,
with conversion methods and price/volume utilities.

Example:
    ```python
    from ctrader_api_client.models import (
        Account,
        Symbol,
        Position,
        NewOrderRequest,
    )
    from ctrader_api_client.enums import OrderType, OrderSide

    # Create an order request
    request = NewOrderRequest(
        symbol_id=1,
        side=OrderSide.BUY,
        volume=100,  # 0.01 lots
        order_type=OrderType.MARKET,
    )
    ```
"""

from .account import Account, AccountSummary
from .deal import CloseDetail, Deal
from .market_data import TickData, Trendbar
from .order import Order
from .position import Position
from .requests import AmendOrderRequest, AmendPositionRequest, ClosePositionRequest, NewOrderRequest
from .symbol import Symbol, SymbolInfo


__all__ = [
    "Account",
    "AccountSummary",
    "AmendOrderRequest",
    "AmendPositionRequest",
    "CloseDetail",
    "ClosePositionRequest",
    "Deal",
    "NewOrderRequest",
    "Order",
    "Position",
    "Symbol",
    "SymbolInfo",
    "TickData",
    "Trendbar",
]
