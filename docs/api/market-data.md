# Market Data API

Real-time market data subscriptions and historical data retrieval.

Access via `client.market_data`.

## MarketDataAPI

::: ctrader_api_client.api.MarketDataAPI
    options:
      show_source: false
      members:
        - subscribe_spots
        - unsubscribe_spots
        - subscribe_trendbars
        - unsubscribe_trendbars
        - subscribe_depth
        - unsubscribe_depth
        - get_trendbars
        - get_tick_data

## Usage Examples

### Subscribe to Spot Prices

```python
from ctrader_api_client import SpotEvent

# Subscribe to symbols
await client.market_data.subscribe_spots(account_id, [270, 271])


# Handle price updates - bid/ask are Decimals
@client.on(SpotEvent, symbol_id=270)
async def on_price(event: SpotEvent):
    print(f"Bid: {event.bid}, Ask: {event.ask}")
```

### Subscribe to Live Trendbars

```python
from ctrader_api_client import SpotEvent, TrendbarPeriod

# Subscribe to M1 trendbars
await client.market_data.subscribe_trendbars(account_id, symbol_id=270, period=TrendbarPeriod.M1)

# Trendbar data is delivered inside SpotEvent
@client.on(SpotEvent, symbol_id=270)
async def on_spot(event: SpotEvent):
    print(f"Price: {event.bid}/{event.ask}")

    # Check if this event contains trendbar data
    if event.trendbar:
        bar = event.trendbar
        print(f"Bar: O={bar.open} H={bar.high} L={bar.low} C={bar.close} V={bar.volume}")
```

### Subscribe to Depth of Market

```python
from ctrader_api_client import DepthEvent

# Subscribe to order book
await client.market_data.subscribe_depth(account_id, symbol_id=270)


@client.on(DepthEvent, symbol_id=270)
async def on_depth(event: DepthEvent):
    for quote in event.new_quotes:
        side = "BID" if quote.is_bid else "ASK"
        print(f"{side}: {quote.price} x {quote.size}")
```

### Get Historical Trendbars

```python
from datetime import datetime, timedelta, UTC
from ctrader_api_client import TrendbarPeriod

trendbars = await client.market_data.get_trendbars(
    account_id,
    symbol_id=270,
    period=TrendbarPeriod.H1,
    from_timestamp=datetime.now(UTC) - timedelta(days=7),
    to_timestamp=datetime.now(UTC),
)

# OHLC values are already Decimals (converted from raw integers)
for bar in trendbars:
    print(f"{bar.timestamp}: O={bar.open} H={bar.high} L={bar.low} C={bar.close} V={bar.volume}")
```

### Get Tick Data

```python
from datetime import datetime, timedelta, UTC

ticks = await client.market_data.get_tick_data(
    account_id,
    symbol_id=270,
    from_timestamp=datetime.now(UTC) - timedelta(hours=1),
    to_timestamp=datetime.now(UTC),
    quote_type="BID",  # or "ASK"
)

# Price is already a Decimal
for tick in ticks:
    print(f"{tick.timestamp}: {tick.price}")
```

### Unsubscribe

```python
# Unsubscribe from spots
await client.market_data.unsubscribe_spots(account_id, [270])

# Unsubscribe from trendbars
await client.market_data.unsubscribe_trendbars(
    account_id,
    symbol_id=270,
    period=TrendbarPeriod.M1,
)

# Unsubscribe from depth
await client.market_data.unsubscribe_depth(account_id, symbol_id=270)
```

## Note on Subscriptions

Subscriptions are restored automatically. `subscribe_spots`, `subscribe_trendbars`
and `subscribe_depth` record what the account asked for, and the client re-applies
it after a reconnection or an account recovery — before the account is announced
as ready, so a `ReadyEvent` handler never sees a half-restored feed. Spots are
re-applied before trendbars, which the server rejects without them.

`unsubscribe_spots`, `unsubscribe_trendbars` and `unsubscribe_depth` withdraw the
intent, so an unsubscribed symbol is not brought back. So does
`client.auth.remove_account`, which discards everything held for that account.

Do not re-subscribe from a `ReadyEvent` handler — the server rejects a duplicate
subscription.

If restoration fails, it stops at the first failure and emits a
`SubscriptionRestoreFailedEvent`. The intent is kept, so the next reconnection
tries again. Until then the account receives no data for the affected symbols:

```python
from ctrader_api_client import SubscriptionRestoreFailedEvent


@client.on(SubscriptionRestoreFailedEvent)
async def on_restore_failed(event: SubscriptionRestoreFailedEvent):
    logger.error("Account %d is missing market data: %s", event.account_id, event.error)
```
