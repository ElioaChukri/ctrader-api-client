# Models

High-level Pythonic models for API requests and responses.

## Request Models

Request for placing a new order.

::: ctrader_api_client.models.NewOrderRequest
    options:
      show_source: false

**Example:**

```python
from ctrader_api_client.models import NewOrderRequest
from ctrader_api_client.enums import OrderType, OrderSide, TimeInForce

# Get symbol for volume conversion
symbol = await client.symbols.get_by_id(account_id, 270)

# Market order
market_order = NewOrderRequest(
    symbol_id=270,
    order_type=OrderType.MARKET,
    side=OrderSide.BUY,
    volume=symbol.lots_to_volume(0.01),  # 0.01 lots
)

# Limit order with SL/TP
limit_order = NewOrderRequest(
    symbol_id=270,
    order_type=OrderType.LIMIT,
    side=OrderSide.BUY,
    volume=symbol.lots_to_volume(0.1),
    limit_price=5000.0,
    stop_loss=4950.0,
    take_profit=5100.0,
    time_in_force=TimeInForce.GOOD_TILL_CANCEL,
)

# Order with relative SL/TP (distance from entry price)
relative_order = NewOrderRequest(
    symbol_id=270,
    order_type=OrderType.MARKET,
    side=OrderSide.BUY,
    volume=symbol.lots_to_volume(0.1),
    relative_stop_loss=50.0,   # 50 price units below entry
    relative_take_profit=100.0,  # 100 price units above entry
)

# Stop order
stop_order = NewOrderRequest(
    symbol_id=270,
    order_type=OrderType.STOP,
    side=OrderSide.SELL,
    volume=symbol.lots_to_volume(0.1),
    stop_price=4900.0,
)
```

::: ctrader_api_client.models.AmendOrderRequest
    options:
      show_source: false

::: ctrader_api_client.models.ClosePositionRequest
    options:
      show_source: false

**Example:**

```python
from ctrader_api_client.models import ClosePositionRequest

# Get position to know its volume
positions = await client.trading.get_open_positions(account_id)
position = positions[0]

# Close entire position
close_all = ClosePositionRequest(
    position_id=position.position_id,
    volume=position.volume,  # Must match position volume for full close
)

# Partial close - close half of the position
symbol = await client.symbols.get_by_id(account_id, position.symbol_id)
current_lots = symbol.volume_to_lots(position.volume)
partial_close = ClosePositionRequest(
    position_id=position.position_id,
    volume=symbol.lots_to_volume(current_lots / 2),  # Close half
)
```

::: ctrader_api_client.models.AmendPositionRequest
    options:
      show_source: false

## Response/Data Models


::: ctrader_api_client.models.Position
    options:
      show_source: false


::: ctrader_api_client.models.Order
    options:
      show_source: false


::: ctrader_api_client.models.Deal
    options:
      show_source: false


::: ctrader_api_client.models.CloseDetail
    options:
      show_source: false


::: ctrader_api_client.models.Symbol
    options:
      show_source: false


::: ctrader_api_client.models.SymbolInfo
    options:
      show_source: false


::: ctrader_api_client.models.Account
    options:
      show_source: false


::: ctrader_api_client.models.AccountSummary
    options:
      show_source: false


::: ctrader_api_client.models.Trendbar
    options:
      show_source: false


::: ctrader_api_client.models.TickData
    options:
      show_source: false

## Volume Conversion

Volumes in the cTrader API are expressed in **cents** relative to the symbol's `lot_size`:

- For standard forex (lot_size=100000): `100000` = 1.0 lots, `10000` = 0.1 lots, `1000` = 0.01 lots
- For other instruments, lot_size may vary

Use the `Symbol` model for conversions:

```python
symbol = await client.symbols.get_by_id(account_id, 270)

# Convert lots to volume for orders
volume = symbol.lots_to_volume(0.1)  # Returns volume in cents

# Convert volume to lots for display
lots = symbol.volume_to_lots(position.volume)  # Returns lots as float
```

## Price Values

Prices in events and models (bid, ask, OHLC, execution prices, etc.) are returned as **floats** - no conversion needed:

```python
@client.on(SpotEvent)
async def on_price(event: SpotEvent):
    # bid and ask are already floats
    spread = event.ask - event.bid
    print(f"Spread: {spread}")

# Trendbar OHLC are floats
for bar in trendbars:
    range_size = bar.high - bar.low
    print(f"Range: {range_size}")

# Account balance is a float
account = await client.accounts.get_trader(account_id)
print(f"Balance: {account.balance}")

# Position values are floats
for pos in positions:
    print(f"Swap: {pos.swap}, Commission: {pos.commission}")
```
