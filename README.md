# cTrader API Client

A Python client for the cTrader Open API. Provides a high-level async interface for trading operations, market data subscriptions, and account management.

Documentation:
- [Library Docs](https://elioachukri.github.io/ctrader-api-client/)
- [cTrader Open API Docs](https://help.ctrader.com/open-api/)

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
from ctrader_api_client import (
    AccountCredentials,
    ClientConfig,
    CTraderClient,
    ReadyEvent,
    SpotEvent,
)

config = ClientConfig(
    client_id="your_client_id",
    client_secret="your_client_secret",
)

client = CTraderClient(config)


@client.on(SpotEvent, symbol_id=270)  # US500.cash
async def on_price(event: SpotEvent):
    print(f"Price update: {event.bid}/{event.ask}")


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

        # Subscribe once. The client re-applies this after any reconnection.
        await client.market_data.subscribe_spots(account_id, [270])

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
# The application is authenticated as the client connects.

# Discover the account behind a trader login
account_id = await client.accounts.resolve_account_id("...", trader_login=12345678)

# Authenticate a trading account
await client.auth.authenticate_trader(
    AccountCredentials(
        account_id=account_id,
        access_token="...",
        refresh_token="...",
        expires_at=1778617423,
    )
)

# Tokens are automatically refreshed before expiry. A refresh that fails is
# retried on the next check rather than dropping the session, and surfaces as a
# TokenRefreshFailedEvent so a persistently dead refresh token is observable.
```

### Persisting Rotated Tokens

Every refresh issues a new access **and** refresh token, and invalidates the old
pair immediately. Pass a `TokenStore` and the client writes each new pair through
as it is issued:

```python
from ctrader_api_client import AccountCredentials, CTraderClient, TokenStore


class PostgresTokenStore(TokenStore):
    def __init__(self, pool):
        self._pool = pool

    async def save(self, credentials: AccountCredentials) -> None:
        await self._pool.execute(
            """
            INSERT INTO ctrader_tokens (account_id, access_token, refresh_token, expires_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (account_id) DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at
            """,
            credentials.account_id,
            credentials.access_token,
            credentials.refresh_token,
            credentials.expires_at,
        )

    # Not part of the protocol. The client never reads the store; you do.
    async def load(self, account_id: int) -> AccountCredentials | None:
        row = await self._pool.fetchrow(
            "SELECT access_token, refresh_token, expires_at FROM ctrader_tokens WHERE account_id = $1",
            account_id,
        )
        if row is None:
            return None
        return AccountCredentials(account_id=account_id, **dict(row))


client = CTraderClient(config, token_store=PostgresTokenStore(pool))
```

The save happens before the new token is put to use. A save that raises aborts
that refresh, which is reported as a `TokenRefreshFailedEvent` and retried on the
next check interval, so a transient storage outage recovers on its own.

The protocol is write-only, because writing is the half the client has to do for
you: rotation happens mid-session, at a moment you cannot observe. Reading back is
yours, since only you know which accounts a given process is responsible for:

```python
store = PostgresTokenStore(pool)
client = CTraderClient(config, token_store=store)

async with client:
    stored = await store.load(account_id)
    if stored is None:
        stored = AccountCredentials(
            account_id=account_id,
            access_token="your_access_token",
            refresh_token="your_refresh_token",
            expires_at=1778617423,
        )

    await client.auth.authenticate_trader(stored)
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
from ctrader_api_client import ClosePositionRequest, NewOrderRequest, OrderSide, OrderType

# Place a market order
request = NewOrderRequest(
    symbol_id=symbol_id,
    order_type=OrderType.MARKET,
    side=OrderSide.BUY,
    volume=100000,  # 1 lot in cents
)
result = await client.trading.place_order(account_id, request)

# Get open positions
positions = await client.trading.get_open_positions(account_id)

# Close a position
close_position = ClosePositionRequest(
    position_id=position_id,
    volume=100000,  # Close full volume
)
await client.trading.close_position(account_id, close_position)
```

### Event Handling

```python
from ctrader_api_client import (
    ExecutionEvent,
    ReadyEvent,
    ReconnectedEvent,
    SpotEvent,
    SubscriptionRestoreFailedEvent,
    TokenRefreshFailedEvent,
)

# Price updates
@client.on(SpotEvent, symbol_id=270)
async def on_spot(event: SpotEvent):
    print(f"{event.bid}/{event.ask}")

# Order executions
@client.on(ExecutionEvent, account_id=account_id)
async def on_execution(event: ExecutionEvent):
    print(f"Order {event.order_id}: {event.execution_type}")

# Account ready (fires on initial auth, after reconnection, and after account-disconnect recovery)
# Subscriptions are already restored by this point; use it to reconcile your own state.
@client.on(ReadyEvent)
async def on_ready(event: ReadyEvent):
    if event.is_reconnect:
        positions = await client.trading.get_open_positions(event.account_id)

# Connection restored
@client.on(ReconnectedEvent)
async def on_reconnected(event: ReconnectedEvent):
    print(f"Reconnected, restored accounts: {event.restored_accounts}")

# Token refresh failed (retried automatically; a repeating event means the
# refresh token is no longer usable and the account must be re-authorized)
@client.on(TokenRefreshFailedEvent, account_id=account_id)
async def on_refresh_failed(event: TokenRefreshFailedEvent):
    print(f"Token refresh failed for {event.account_id}: {event.error}")

# Market data could not be re-applied after a reconnection (retried on the next one)
@client.on(SubscriptionRestoreFailedEvent, account_id=account_id)
async def on_restore_failed(event: SubscriptionRestoreFailedEvent):
    print(f"Account {event.account_id} is missing market data: {event.error}")
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
3. Re-applies each account's market data subscriptions
4. Emits `ReadyEvent` for each restored account
5. Emits `ReconnectedEvent` with summary of restored/failed accounts

It also handles **server-side account disconnects** (e.g. a broker dropping the
account session over the weekend while the connection stays up): the account is
re-authenticated on the existing connection with backoff until it succeeds, its
subscriptions are re-applied, and then a `ReadyEvent` is emitted. Account
authorization is observable via `client.is_account_authorized(account_id)`,
which is distinct from the transport-level `client.is_connected`.

Subscribe once, when you first authenticate. The client remembers what each
account asked for and re-applies it before announcing the account as ready, so
do not re-subscribe from a `ReadyEvent` handler — the server rejects a duplicate
subscription. If restoration fails it stops at the first failure and emits a
`SubscriptionRestoreFailedEvent`, keeping the intent so the next reconnection
tries again.

## Configuration

```python
from ctrader_api_client import ClientConfig, ReauthPolicy, RefreshPolicy

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

    # Token refresh: when to refresh access tokens and how hard to retry
    refresh_policy=RefreshPolicy(
        buffer_seconds=300.0,  # refresh this long before expiry
        check_interval=60.0,   # how often to check for expiring tokens
        retry_attempts=3,
        retry_min_wait=1.0,
        retry_max_wait=30.0,
    ),

    # Session recovery: backoff for re-establishing sessions the server dropped
    reauth_policy=ReauthPolicy(
        min_wait=1.0,
        max_wait=60.0,
    ),
)
```
