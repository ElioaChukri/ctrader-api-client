# Events

The client uses an event-driven architecture. Register handlers with `@client.on()` to receive real-time updates.

## Registering Handlers

```python
from ctrader_api_client import ExecutionEvent, SpotEvent

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
| SubscriptionRestoreFailedEvent | Yes | No |
| ReconnectedEvent | No | No |
| ClientDisconnectEvent | No | No |

Using an unsupported filter raises `ValueError` at registration time.

## Market Data Events

::: ctrader_api_client.events.SpotEvent
    options:
      show_source: false

**SpotEvent contains live trendbar data when subscribed:**

```python
from ctrader_api_client import TrendbarPeriod

# Subscribe to both spot prices and M1 trendbars
await client.market_data.subscribe_spots(account_id, [270])
await client.market_data.subscribe_trendbars(account_id, 270, TrendbarPeriod.M1)

@client.on(SpotEvent, symbol_id=270)
async def on_spot(event: SpotEvent):
    # Prices are Decimals
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

**Use this to reconcile account state after an interruption.** It fires on
initial auth, after a transport reconnection, and after recovery from a
server-side account disconnect — `is_reconnect` is `True` for the latter two:

```python
@client.on(ReadyEvent)
async def on_ready(event: ReadyEvent):
    if event.is_reconnect:
        # Market data subscriptions are already restored. Positions opened or
        # orders filled while disconnected produced events you never saw.
        positions = await client.trading.get_open_positions(event.account_id)
        my_book.replace(positions)
```

Market data subscriptions are re-applied before this event is emitted, so do not
re-subscribe here — the server rejects a duplicate subscription.

`event.trigger` carries the exact reason as an `AuthTrigger`, for cases where
`is_reconnect` is too coarse. The event is emitted for `INITIAL`, `RECONNECT`,
and `ACCOUNT_REAUTH` (all of which lose or re-establish subscriptions), and
suppressed for `TOKEN_REFRESH` (session intact).

::: ctrader_api_client.enums.AuthTrigger
    options:
      show_source: false
      members: true

::: ctrader_api_client.events.TraderUpdateEvent
    options:
      show_source: false

::: ctrader_api_client.events.MarginChangeEvent
    options:
      show_source: false

::: ctrader_api_client.events.MarginCallTriggerEvent
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

The client recovers from this automatically — it re-authenticates the account on
the existing connection with backoff and emits a `ReadyEvent` on success. The
event is informational; subscribe to it only if you want to observe or log the
drop. Check current authorization with `client.is_account_authorized(account_id)`.

A disconnect the server reports is checked before it is published. Rotating an
access token makes the server report one for a session it has not ended, so the
client asks whether the account is still served on this connection: if it is,
nothing is published. The check does not re-authenticate, because that answers
for the token as much as for the session, and the rotation prompting the report
is the very thing that would make such an answer unreliable.

The check also waits for any token refresh on that account to finish first.
Rotating a token means the server drops the old authorization and the client
establishes a new one, and in between the account is genuinely unauthorized — it
refuses everything, including the check. Since the refresh always begins before
the report it provokes, waiting for it to settle is what keeps a moment the
client itself created from reading as a lost session.

A check that cannot be completed — a timeout, a link that has just gone — is not
read as a disconnect either. The account is left as it was, and the next report
is checked afresh. What reaches a handler is therefore always a session the
server confirmed it was no longer serving.

::: ctrader_api_client.events.TokenInvalidatedEvent
    options:
      show_source: false

::: ctrader_api_client.events.TokenRefreshFailedEvent
    options:
      show_source: false

The client keeps the existing credentials and retries on the next refresh check,
so a single event usually means a transient outage. If the event keeps repeating,
the refresh token is no longer usable and the account has to be re-authorized out
of band.

::: ctrader_api_client.events.SubscriptionRestoreFailedEvent
    options:
      show_source: false

Emitted when the client could not re-apply an account's market data
subscriptions to a new session. Restoration stops at the first failure, so
anything after it in the sequence is missing too. The intent is kept and the
next reconnection tries again, but until then the account receives no data for
the affected symbols. Re-subscribe from a handler if you need it sooner.

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
