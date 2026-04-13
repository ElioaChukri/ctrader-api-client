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

# Market order
market_order = NewOrderRequest(
    symbol_id=270,
    order_type=OrderType.MARKET,
    side=OrderSide.BUY,
    volume=100,  # 0.01 lots
)

# Limit order with SL/TP
limit_order = NewOrderRequest(
    symbol_id=270,
    order_type=OrderType.LIMIT,
    side=OrderSide.BUY,
    volume=100,
    limit_price=5000.0,
    stop_loss=4950.0,
    take_profit=5100.0,
    time_in_force=TimeInForce.GOOD_TILL_CANCEL,
)

# Stop order
stop_order = NewOrderRequest(
    symbol_id=270,
    order_type=OrderType.STOP,
    side=OrderSide.SELL,
    volume=100,
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

# Close entire position
close_all = ClosePositionRequest(
    position_id=123456,
    volume=100,  # Must match position volume for full close
)

# Partial close
partial_close = ClosePositionRequest(
    position_id=123456,
    volume=50,  # Close half
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

## Volume and Price Conversion

Volumes in the cTrader API are expressed in **cents** (1/100 of the base unit):

- `100` = 0.01 lots
- `10000` = 0.1 lots
- `100000` = 1.0 lot

Use the `Symbol` model for conversions:

```python
symbol = await client.symbols.get_by_id(account_id, 270)

# Convert volume to lots
volume_in_cents = 100
lots = symbol.volume_to_lots(volume_in_cents)  # 1.0

# Convert lots to volume
lots = 0.5
volume = symbol.lots_to_volume(lots)  # 50
```

Prices are returned as raw integers. Use the symbol's `digits` for conversion:

```python
# Raw price from event
raw_price = event.bid  # e.g., 123456

# Convert to decimal
decimal_price = Decimal(raw_price) / Decimal(10 ** 5)  # 1.23456
```
