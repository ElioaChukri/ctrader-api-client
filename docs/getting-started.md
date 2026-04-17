# Getting Started

This guide walks you through setting up and using the cTrader API Client.

## Prerequisites

1. A cTrader trading account (demo or live)
2. OAuth credentials from [cTrader Open API](https://openapi.ctrader.com/)
3. Python 3.12+

## Installation

```bash
uv add ctrader-api-client
```

Or with pip:

```bash
pip install ctrader-api-client
```

## OAuth Token Generation

This library requires OAuth tokens from cTrader. For development, you can use [ctrader-oauth-fetcher](https://github.com/ElioaChukri/ctrader-oauth-fetcher):

```bash
uvx ctrader-oauth-fetcher --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
```

This opens a browser for authorization and returns your access token, refresh token, and expiry timestamp.

For production applications, implement the full OAuth flow according to the [cTrader Open API documentation](https://help.ctrader.com/open-api/).

## Basic Usage

### 1. Create a Client

```python
from ctrader_api_client import CTraderClient, ClientConfig

config = ClientConfig(
    client_id="your_client_id",
    client_secret="your_client_secret",
)

client = CTraderClient(config)
```

### 2. Connect and Authenticate

```python
async with client:
    # Authenticate the application
    await client.auth.authenticate_app()

    # Authenticate a trading account
    creds = await client.auth.authenticate_by_trader_login(
        trader_login=12345678,  # Your trader login number
        access_token="your_access_token",
        refresh_token="your_refresh_token",
        expires_at=1778617423,  # Unix timestamp
    )

    # Now you can use creds.account_id for API calls
    print(f"Authenticated account: {creds.account_id}")
```

### 3. Subscribe to Market Data

```python
from ctrader_api_client.events import SpotEvent

@client.on(SpotEvent, symbol_id=270)  # US500.cash
async def on_price(event: SpotEvent):
    print(f"Bid: {event.bid}, Ask: {event.ask}")

# Subscribe after authentication
await client.market_data.subscribe_spots(creds.account_id, [270])
```

### 4. Place Orders

```python
from ctrader_api_client.models import NewOrderRequest
from ctrader_api_client.enums import OrderType, OrderSide

# Get symbol info for volume conversion
symbol = await client.symbols.get_by_id(creds.account_id, 270)

request = NewOrderRequest(
    symbol_id=270,
    order_type=OrderType.MARKET,
    side=OrderSide.BUY,
    volume=symbol.lots_to_volume(0.01),  # Convert 0.01 lots to volume
)

result = await client.trading.place_order(creds.account_id, request)
print(f"Order {result.order_id}: {result.execution_type}")
```

## Complete Example

```python
import asyncio
from ctrader_api_client import CTraderClient, ClientConfig
from ctrader_api_client.events import ReadyEvent, SpotEvent, ExecutionEvent
from ctrader_api_client.models import NewOrderRequest
from ctrader_api_client.enums import OrderType, OrderSide

config = ClientConfig(
    client_id="your_client_id",
    client_secret="your_client_secret",
)

client = CTraderClient(config)


@client.on(ReadyEvent)
async def on_ready(event: ReadyEvent):
    """Called when account is authenticated (initial or after reconnect)."""
    print(f"Account {event.account_id} ready")
    await client.market_data.subscribe_spots(event.account_id, [270])


@client.on(SpotEvent, symbol_id=270)
async def on_price(event: SpotEvent):
    """Called on each price tick."""
    print(f"Price: {event.bid}/{event.ask}")


@client.on(ExecutionEvent)
async def on_execution(event: ExecutionEvent):
    """Called when orders are executed."""
    print(f"Execution: {event.execution_type} for order {event.order_id}")


async def main():
    async with client:
        await client.auth.authenticate_app()
        creds = await client.auth.authenticate_by_trader_login(
            trader_login=12345678,
            access_token="your_access_token",
            refresh_token="your_refresh_token",
            expires_at=1778617423,
        )

        # Get symbol for volume conversion
        symbol = await client.symbols.get_by_id(creds.account_id, 270)

        # Place a test order
        order = NewOrderRequest(
            symbol_id=270,
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            volume=symbol.lots_to_volume(0.01),  # 0.01 lots
        )
        await client.trading.place_order(creds.account_id, order)

        # Keep running to receive events
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
```

## Handling Reconnections

The client automatically reconnects when the connection drops. Use `ReadyEvent` to restore subscriptions:

```python
@client.on(ReadyEvent)
async def on_ready(event: ReadyEvent):
    """Called on initial auth AND after reconnection."""
    # Set up subscriptions here - they persist across reconnects
    await client.market_data.subscribe_spots(event.account_id, [270, 271, 272])

    if event.is_reconnect:
        print("Connection restored!")
```

For additional reconnection information:

```python
from ctrader_api_client.events import ReconnectedEvent

@client.on(ReconnectedEvent)
async def on_reconnected(event: ReconnectedEvent):
    print(f"Reconnected. Restored accounts: {event.restored_accounts}")
    if event.failed_accounts:
        print(f"Failed accounts: {event.failed_accounts}")
```

## Configuration Options

```python
config = ClientConfig(
    client_id="your_client_id",
    client_secret="your_client_secret",

    # Connection settings
    host="live.ctraderapi.com",  # or "demo.ctraderapi.com"
    port=5035,
    use_ssl=True,

    # Timeouts
    heartbeat_interval=10.0,
    heartbeat_timeout=0,  # 0 to disable server heartbeat checks (default)
    request_timeout=30.0,

    # Reconnection
    reconnect_attempts=5,
    reconnect_min_wait=1.0,
    reconnect_max_wait=60.0,
)
```

## Next Steps

- [API Reference - Client](api/client.md) - Full client documentation
- [API Reference - Trading](api/trading.md) - Order and position operations
- [API Reference - Events](api/events.md) - All available events
- [API Reference - Models](api/models.md) - Request and response models
