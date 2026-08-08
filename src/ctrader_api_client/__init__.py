"""cTrader Open API Python client.

A high-level async client for the cTrader trading platform.

Everything a caller names is re-exported here: what you construct, what you
receive, and what you catch. The machinery behind them stays in its
subpackages, since the client wires it for you.

Example:
    ```python
    import asyncio
    from ctrader_api_client import AccountCredentials, ClientConfig, CTraderClient, SpotEvent

    config = ClientConfig(
        client_id="your_client_id",
        client_secret="your_client_secret",
    )

    client = CTraderClient(config)


    @client.on(SpotEvent, symbol_id=270)
    async def on_spot(event: SpotEvent) -> None:
        print(f"{event.bid}/{event.ask}")


    async def main():
        async with client:
            account_id = await client.accounts.resolve_account_id("...", trader_login=17091452)
            await client.auth.authenticate_trader(
                AccountCredentials(
                    account_id=account_id,
                    access_token="...",
                    refresh_token="...",
                    expires_at=1778617423,
                )
            )
            await client.market_data.subscribe_spots(account_id, [270])
            await asyncio.Event().wait()


    asyncio.run(main())
    ```
"""

from .auth import AccountCredentials, ReauthPolicy, RefreshPolicy, TokenStore
from .client import CTraderClient
from .config import ClientConfig
from .enums import (
    AccessRights,
    AccountType,
    AuthTrigger,
    DealStatus,
    ExecutionType,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionStatus,
    StopTriggerMethod,
    TimeInForce,
    TradingMode,
    TrendbarPeriod,
)
from .events import (
    AccountDisconnectEvent,
    ClientDisconnectEvent,
    DepthEvent,
    DepthQuote,
    Event,
    ExecutionEvent,
    MarginCallTriggerEvent,
    MarginChangeEvent,
    OrderErrorEvent,
    ReadyEvent,
    ReconnectedEvent,
    SpotEvent,
    SubscriptionRestoreFailedEvent,
    SymbolChangedEvent,
    TokenInvalidatedEvent,
    TokenRefreshFailedEvent,
    TraderUpdateEvent,
    TrailingStopChangedEvent,
)
from .exceptions import (
    AccountAuthError,
    AccountNotFoundError,
    APIError,
    ApplicationAuthError,
    AuthenticationError,
    CTraderConnectionClosedError,
    CTraderConnectionError,
    CTraderConnectionFailedError,
    CTraderConnectionTimeoutError,
    CTraderError,
    CTraderReconnectAbandonedError,
    DeserializationError,
    FramingError,
    ProtocolError,
    TokenExpiredError,
    TokenRefreshError,
    UnknownPayloadTypeError,
)
from .models import (
    Account,
    AccountSummary,
    AmendOrderRequest,
    AmendPositionRequest,
    CloseDetail,
    ClosePositionRequest,
    Deal,
    NewOrderRequest,
    Order,
    Position,
    PositionUnrealizedPnL,
    Symbol,
    SymbolInfo,
    TickData,
    Trendbar,
)


__all__ = [
    "APIError",
    "AccessRights",
    "Account",
    "AccountAuthError",
    "AccountCredentials",
    "AccountDisconnectEvent",
    "AccountNotFoundError",
    "AccountSummary",
    "AccountType",
    "AmendOrderRequest",
    "AmendPositionRequest",
    "ApplicationAuthError",
    "AuthTrigger",
    "AuthenticationError",
    "CTraderClient",
    "CTraderConnectionClosedError",
    "CTraderConnectionError",
    "CTraderConnectionFailedError",
    "CTraderConnectionTimeoutError",
    "CTraderError",
    "CTraderReconnectAbandonedError",
    "ClientConfig",
    "ClientDisconnectEvent",
    "CloseDetail",
    "ClosePositionRequest",
    "Deal",
    "DealStatus",
    "DepthEvent",
    "DepthQuote",
    "DeserializationError",
    "Event",
    "ExecutionEvent",
    "ExecutionType",
    "FramingError",
    "MarginCallTriggerEvent",
    "MarginChangeEvent",
    "NewOrderRequest",
    "Order",
    "OrderErrorEvent",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "PositionStatus",
    "PositionUnrealizedPnL",
    "ProtocolError",
    "ReadyEvent",
    "ReauthPolicy",
    "ReconnectedEvent",
    "RefreshPolicy",
    "SpotEvent",
    "StopTriggerMethod",
    "SubscriptionRestoreFailedEvent",
    "Symbol",
    "SymbolChangedEvent",
    "SymbolInfo",
    "TickData",
    "TimeInForce",
    "TokenExpiredError",
    "TokenInvalidatedEvent",
    "TokenRefreshError",
    "TokenRefreshFailedEvent",
    "TokenStore",
    "TraderUpdateEvent",
    "TradingMode",
    "TrailingStopChangedEvent",
    "Trendbar",
    "TrendbarPeriod",
    "UnknownPayloadTypeError",
]
