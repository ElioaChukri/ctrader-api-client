# cTrader API Client

A Python client for the cTrader Open API. Provides a high-level async interface for trading operations, market data subscriptions, and account management.

> Note that this library is in early development. The API may change, and some features may be incomplete. Contributions and feedback are welcome!

## Requirements

- Python 3.12+
- An activated cTrader Open API application with client ID and secret
- OAuth tokens for account authentication (see below)

## Installation

**Using uv (recommended):**

```bash
uv add ctrader-api-client
```

**Using pip:**

```bash
pip install ctrader-api-client
```

## Quick Start

```python
import asyncio
from ctrader_api_client import CTraderClient, ClientConfig
from ctrader_api_client.events import ReadyEvent, SpotEvent

config = ClientConfig(
    client_id="your_client_id",
    client_secret="your_client_secret",
)

client = CTraderClient(config)


@client.on(SpotEvent, symbol_id=270)  # US500.cash
async def on_price(event: SpotEvent):
    print(f"Price update: {event.bid}/{event.ask}")


@client.on(ReadyEvent)
async def on_ready(event: ReadyEvent):
    """Called when account is authenticated and ready."""
    await client.market_data.subscribe_spots(event.account_id, [270])


async def main():
    async with client:
        await client.auth.authenticate_app()
        await client.auth.authenticate_by_trader_login(
            trader_login=12345678,
            access_token="your_access_token",
            refresh_token="your_refresh_token",
            expires_at=1778617423,
        )

        # Keep running to receive events
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
```

## OAuth Token Generation

This library requires OAuth tokens from cTrader. For simple use cases, you can use [ctrader-oauth-fetcher](https://github.com/ElioaChukri/ctrader-oauth-fetcher) to generate tokens:

```bash
uvx ctrader-oauth-fetcher --client-id [ID] --client-secret [SECRET]
```

This opens a browser for authorization and returns your access token, refresh token, and expiry time.

For production applications, implement the OAuth flow according to the [cTrader Open API documentation](https://help.ctrader.com/open-api/).

## Features

### Authentication

```python
# Authenticate the application
await client.auth.authenticate_app()

# Authenticate a trading account
creds = await client.auth.authenticate_by_trader_login(
    trader_login=12345678,
    access_token="...",
    refresh_token="...",
    expires_at=1778617423,
)

# Tokens are automatically refreshed before expiry
```

### Market Data

```python
# Subscribe to spot prices
await client.market_data.subscribe_spots(account_id, [symbol_id])

# Subscribe to candles
await client.market_data.subscribe_trendbars(account_id, symbol_id, TrendbarPeriod.M1)

# Get historical data
bars = await client.market_data.get_trendbars(
    account_id, symbol_id, TrendbarPeriod.H1, from_ts, to_ts
)
```

### Trading

```python
from ctrader_api_client.models import NewOrderRequest, ClosePositionRequest
from ctrader_api_client.enums import OrderType, OrderSide

# Place a market order
request = NewOrderRequest(
    symbol_id=symbol_id,
    order_type=OrderType.MARKET,
    side=OrderSide.BUY,
    volume=100000,  # 1 lot in cents
)
result = await client.trading.create_order(account_id, request)

# Get open positions
positions = await client.trading.get_positions(account_id)

# Close a position
close_position = ClosePositionRequest(
    position_id=position_id,
    volume=100000,  # Close full volume
)
await client.trading.close_position(account_id, close_position)
```

### Event Handling

```python
from ctrader_api_client.events import (
    SpotEvent,
    ExecutionEvent,
    ReadyEvent,
    ReconnectedEvent,
)

# Price updates
@client.on(SpotEvent, symbol_id=270)
async def on_spot(event: SpotEvent):
    print(f"{event.bid}/{event.ask}")

# Order executions
@client.on(ExecutionEvent, account_id=account_id)
async def on_execution(event: ExecutionEvent):
    print(f"Order {event.order_id}: {event.execution_type}")

# Account ready (fires on initial auth and after reconnection)
@client.on(ReadyEvent)
async def on_ready(event: ReadyEvent):
    # Set up subscriptions here
    await client.market_data.subscribe_spots(event.account_id, symbols)

# Connection restored
@client.on(ReconnectedEvent)
async def on_reconnected(event: ReconnectedEvent):
    print(f"Reconnected, restored accounts: {event.restored_accounts}")
```

### Symbols

```python
# List all symbols
symbols = await client.symbols.list_all(account_id)

# Search by name
results = await client.symbols.search(account_id, "EUR")

# Get specific symbol
symbol = await client.symbols.get_by_id(account_id, symbol_id)
```

### Account Information

```python
# Get account details
account = await client.accounts.get_trader(account_id)
print(f"Balance: {account.balance}")
```

## Automatic Reconnection

The client automatically handles connection drops:

1. Reconnects with exponential backoff
2. Re-authenticates the app and all accounts
3. Emits `ReadyEvent` for each restored account (for resubscribing to market data)
4. Emits `ReconnectedEvent` with summary of restored/failed accounts

Use `ReadyEvent` to set up subscriptions that persist across reconnections.

## Configuration

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
    heartbeat_timeout=30.0, # Or 0 to disable server heartbeat checks
    request_timeout=30.0,

    # Reconnection
    reconnect_attempts=5,
    reconnect_min_wait=1.0,
    reconnect_max_wait=60.0,
)
```
