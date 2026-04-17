# Events

The client uses an event-driven architecture. Register handlers with `@client.on()` to receive real-time updates.

## Registering Handlers

```python
from ctrader_api_client.events import SpotEvent, ExecutionEvent

@client.on(SpotEvent, symbol_id=270)  # Filter by symbol
async def on_spot(event: SpotEvent):
    print(f"{event.bid}/{event.ask}")


@client.on(ExecutionEvent, account_id=12345)  # Filter by account
async def on_execution(event: ExecutionEvent):
    print(f"Order {event.order_id}: {event.execution_type}")
```

### Filtering

Different events support different filters:

| Event | `account_id` | `symbol_id` |
|-------|--------------|-------------|
| SpotEvent | Yes | Yes |
| ExecutionEvent | Yes | Yes |
| DepthEvent | Yes | Yes |
| ReadyEvent | Yes | No |
| OrderErrorEvent | Yes | No |
| TraderUpdateEvent | Yes | No |
| MarginChangeEvent | Yes | No |
| ReconnectedEvent | No | No |
| ClientDisconnectEvent | No | No |

Using an unsupported filter raises `ValueError` at registration time.

## Market Data Events

::: ctrader_api_client.events.SpotEvent
    options:
      show_source: false

**SpotEvent contains live trendbar data when subscribed:**

```python
from ctrader_api_client.enums import TrendbarPeriod

# Subscribe to both spot prices and M1 trendbars
await client.market_data.subscribe_spots(account_id, [270])
await client.market_data.subscribe_trendbars(account_id, 270, TrendbarPeriod.M1)

@client.on(SpotEvent, symbol_id=270)
async def on_spot(event: SpotEvent):
    # Prices are floats
    print(f"Bid: {event.bid}, Ask: {event.ask}")

    # Trendbar is included when subscribed
    if event.trendbar:
        bar = event.trendbar
        print(f"Candle: O={bar.open} H={bar.high} L={bar.low} C={bar.close}")
```

::: ctrader_api_client.events.DepthEvent
    options:
      show_source: false

::: ctrader_api_client.events.DepthQuote
    options:
      show_source: false

## Trading Events

::: ctrader_api_client.events.ExecutionEvent
    options:
      show_source: false

::: ctrader_api_client.events.OrderErrorEvent
    options:
      show_source: false

## Account Events

::: ctrader_api_client.events.ReadyEvent
    options:
      show_source: false

**Use this to set up subscriptions that persist across reconnections:**

```python
@client.on(ReadyEvent)
async def on_ready(event: ReadyEvent):
    await client.market_data.subscribe_spots(event.account_id, [270])

    if event.is_reconnect:
        print("Connection restored!")
```

::: ctrader_api_client.events.TraderUpdateEvent
    options:
      show_source: false

::: ctrader_api_client.events.MarginChangeEvent
    options:
      show_source: false

::: ctrader_api_client.events.MarginCallTriggerEvent
    options:
      show_source: false

::: ctrader_api_client.events.PnLChangeEvent
    options:
      show_source: false

::: ctrader_api_client.events.TrailingStopChangedEvent
    options:
      show_source: false

## Connection Events

::: ctrader_api_client.events.ReconnectedEvent
    options:
      show_source: false

**Example:**

```python
@client.on(ReconnectedEvent)
async def on_reconnected(event: ReconnectedEvent):
    print(f"Reconnected! App auth: {event.app_auth_restored}")
    print(f"Restored accounts: {event.restored_accounts}")
    if event.failed_accounts:
        print(f"Failed accounts: {event.failed_accounts}")
```

::: ctrader_api_client.events.ClientDisconnectEvent
    options:
      show_source: false

::: ctrader_api_client.events.AccountDisconnectEvent
    options:
      show_source: false

::: ctrader_api_client.events.TokenInvalidatedEvent
    options:
      show_source: false

## Symbol Events

::: ctrader_api_client.events.SymbolChangedEvent
    options:
      show_source: false

## Unregistering Handlers

```python
@client.on(SpotEvent)
async def my_handler(event: SpotEvent):
    ...

# Later, unregister
client.off(SpotEvent, my_handler)
```
