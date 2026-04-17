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
from ctrader_api_client.events import SpotEvent

# Subscribe to symbols
await client.market_data.subscribe_spots(account_id, [270, 271])


# Handle price updates - bid/ask are floats
@client.on(SpotEvent, symbol_id=270)
async def on_price(event: SpotEvent):
    print(f"Bid: {event.bid}, Ask: {event.ask}")
```

### Subscribe to Live Trendbars

```python
from ctrader_api_client.events import SpotEvent
from ctrader_api_client.enums import TrendbarPeriod

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
from ctrader_api_client.events import DepthEvent

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
from ctrader_api_client.enums import TrendbarPeriod

trendbars = await client.market_data.get_trendbars(
    account_id,
    symbol_id=270,
    period=TrendbarPeriod.H1,
    from_timestamp=datetime.now(UTC) - timedelta(days=7),
    to_timestamp=datetime.now(UTC),
)

# OHLC values are already floats (converted from raw integers)
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

# Price is already a float
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

Subscriptions are **not** automatically restored after reconnection.
It is recommended to use `ReadyEvent` to keep all subscriptions centralized in one place and ensure they are re-established after any disconnects.

```python
from ctrader_api_client.events import ReadyEvent
from ctrader_api_client.enums import TrendbarPeriod

@client.on(ReadyEvent)
async def on_ready(event: ReadyEvent):
    # This runs on initial auth AND after reconnection
    await client.market_data.subscribe_spots(event.account_id, [270, 271])
    await client.market_data.subscribe_trendbars(event.account_id, 270, TrendbarPeriod.M1)
```
