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

The application is authenticated as the client connects, so all that is left is
the trading account.

```python
from ctrader_api_client import AccountCredentials

async with client:
    # Discover the account behind a trader login
    account_id = await client.accounts.resolve_account_id(
        "your_access_token",
        trader_login=12345678,  # Your trader login number
    )

    # Authenticate the trading account
    await client.auth.authenticate_trader(
        AccountCredentials(
            account_id=account_id,
            access_token="your_access_token",
            refresh_token="your_refresh_token",
            expires_at=1778617423,  # Unix timestamp
        )
    )

    print(f"Authenticated account: {account_id}")
```

### 3. Subscribe to Market Data

```python
from ctrader_api_client import SpotEvent

@client.on(SpotEvent, symbol_id=270)  # US500.cash
async def on_price(event: SpotEvent):
    print(f"Bid: {event.bid}, Ask: {event.ask}")

# Subscribe after authentication
await client.market_data.subscribe_spots(account_id, [270])
```

### 4. Place Orders

```python
from ctrader_api_client import NewOrderRequest, OrderSide, OrderType

# Get symbol info for volume conversion
symbol = await client.symbols.get_by_id(account_id, 270)

request = NewOrderRequest(
    symbol_id=270,
    order_type=OrderType.MARKET,
    side=OrderSide.BUY,
    volume=symbol.lots_to_volume(0.01),  # Convert 0.01 lots to volume
)

result = await client.trading.place_order(account_id, request)
print(f"Order {result.order_id}: {result.execution_type}")
```

## Complete Example

```python
import asyncio
from ctrader_api_client import (
    AccountCredentials,
    ClientConfig,
    CTraderClient,
    ExecutionEvent,
    NewOrderRequest,
    OrderSide,
    OrderType,
    ReadyEvent,
    SpotEvent,
)

config = ClientConfig(
    client_id="your_client_id",
    client_secret="your_client_secret",
)

client = CTraderClient(config)


@client.on(ReadyEvent)
async def on_ready(event: ReadyEvent):
    """Called when account is authenticated (initial or after reconnect)."""
    print(f"Account {event.account_id} ready")


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
        account_id = await client.accounts.resolve_account_id(
            "your_access_token",
            trader_login=12345678,
        )
        await client.auth.authenticate_trader(
            AccountCredentials(
                account_id=account_id,
                access_token="your_access_token",
                refresh_token="your_refresh_token",
                expires_at=1778617423,
            )
        )

        # Get symbol for volume conversion
        symbol = await client.symbols.get_by_id(account_id, 270)

        # Subscribe once. The client re-applies this after any reconnection.
        await client.market_data.subscribe_spots(account_id, [270])

        # Place a test order
        order = NewOrderRequest(
            symbol_id=270,
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            volume=symbol.lots_to_volume(0.01),  # 0.01 lots
        )
        await client.trading.place_order(account_id, order)

        # Keep running to receive events
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
```

## Persisting Tokens

The examples above hold their tokens in the source, which is fine while you are
finding your feet and wrong for anything long-running.

cTrader rotates both the access token and the refresh token on every refresh and
invalidates the old pair immediately. A process that restarts holding the pair it
was originally given cannot authenticate. Pass a `TokenStore` and the client
writes each new pair through as it is issued:

```python
from ctrader_api_client import AccountCredentials, TokenStore


class FileTokenStore(TokenStore):
    def __init__(self, path: Path) -> None:
        self._path = path

    async def save(self, credentials: AccountCredentials) -> None:
        self._path.write_text(json.dumps(asdict(credentials)))

    # Not part of the protocol. The client never reads the store; you do.
    async def load(self) -> AccountCredentials | None:
        if not self._path.exists():
            return None
        return AccountCredentials(**json.loads(self._path.read_text()))


store = FileTokenStore(Path("tokens.json"))
client = CTraderClient(config, token_store=store)

async with client:
    credentials = await store.load()
    if credentials is None:
        credentials = AccountCredentials(
            account_id=account_id,
            access_token="your_access_token",
            refresh_token="your_refresh_token",
            expires_at=1778617423,
        )

    await client.auth.authenticate_trader(credentials)
```

The contract is write-only. Reading back at startup is yours, since only you know
which accounts a given process is responsible for. See
[TokenStore](api/client.md#tokenstore) for the full contract.

## Handling Errors

Everything the library raises derives from `CTraderError`. Bringing the client up
connects and authenticates the application, so those are the two failures
`async with` raises:

```python
from ctrader_api_client import ApplicationAuthError, CTraderConnectionFailedError

try:
    async with client:
        ...
except CTraderConnectionFailedError as e:
    print(f"Could not reach {e.host}:{e.port}")
except ApplicationAuthError as e:
    print(f"Application rejected: {e.error_code}")
```

Failures that happen outside a call you made — a token refresh giving up, a
subscription that could not be restored — arrive as events instead. See
[Exceptions](api/exceptions.md) for the full picture.

## Handling Reconnections

The client automatically reconnects when the connection drops, and also recovers
from server-side account disconnects (where the account session is dropped but
the connection stays up). In both cases it re-authenticates, re-applies the
account's market data subscriptions, and emits a `ReadyEvent`.

Subscriptions are handled for you, so a `ReadyEvent` handler is where you repair
what the client cannot: positions opened, orders filled or margin changed while
you were disconnected produced execution events you never saw, so your own view
of the account may have drifted.

```python
@client.on(ReadyEvent)
async def on_ready(event: ReadyEvent):
    """Called on initial auth, after reconnection, and after account recovery."""
    if event.is_reconnect:
        # Subscriptions are already back; reconcile state the client cannot.
        positions = await client.trading.get_open_positions(event.account_id)
        my_book.replace(positions)
```

You can check whether an account currently has a live, authorized session with
`client.is_account_authorized(account_id)` — distinct from the transport-level
`client.is_connected`.

For additional reconnection information:

```python
from ctrader_api_client import ReconnectedEvent

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

    # Reconnection: None retries for as long as the client is open (the
    # default), an integer caps the attempts, 0 disables reconnection.
    reconnect_attempts=None,
    reconnect_min_wait=1.0,
    reconnect_max_wait=60.0,
    connect_timeout=30.0,
)
```

Reconnection is unbounded by default because a finite budget that runs out
leaves a client that can never recover: there is no reader and no heartbeat left
to notice anything, so it stays offline until the process restarts. If you do
set a finite `reconnect_attempts`, spending it raises
`CTraderReconnectAbandonedError` out of the `async with client:` block rather
than leaving the client alive and permanently disconnected.

## Next Steps

- [API Reference - Client](api/client.md) - Full client documentation
- [API Reference - Trading](api/trading.md) - Order and position operations
- [API Reference - Events](api/events.md) - All available events
- [API Reference - Models](api/models.md) - Request and response models
- [API Reference - Exceptions](api/exceptions.md) - Errors and how they surface
