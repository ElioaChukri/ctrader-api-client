# Trading API

Order placement, modification, cancellation, and position management.

Access via `client.trading`.

## TradingAPI

::: ctrader_api_client.api.TradingAPI
    options:
      show_source: false
      members:
        - place_order
        - amend_order
        - cancel_order
        - close_position
        - amend_position
        - get_open_positions
        - get_pending_orders
        - get_deals
        - get_deals_by_position_id

## Usage Examples

### Place a Market Order

```python
from ctrader_api_client.models import NewOrderRequest
from ctrader_api_client.enums import OrderType, OrderSide

# Get symbol info for volume conversion
symbol = await client.symbols.get_by_id(account_id, 270)

# Place a 0.1 lot buy order
request = NewOrderRequest(
    symbol_id=270,
    order_type=OrderType.MARKET,
    side=OrderSide.BUY,
    volume=symbol.lots_to_volume(0.1),  # Convert lots to volume
)

result = await client.trading.place_order(account_id, request)
print(f"Order {result.order_id}: {result.execution_type}")
```

### Place a Limit Order

```python
# Get symbol info
symbol = await client.symbols.get_by_id(account_id, 270)

request = NewOrderRequest(
    symbol_id=270,
    order_type=OrderType.LIMIT,
    side=OrderSide.BUY,
    volume=symbol.lots_to_volume(0.1),
    limit_price=5000.0,  # Limit price
    stop_loss=4950.0,  # Optional SL
    take_profit=5100.0,  # Optional TP
)

result = await client.trading.place_order(account_id, request)
```

### Place an Order with Relative SL/TP

```python
# Relative SL/TP are specified in price units (distance from entry)
request = NewOrderRequest(
    symbol_id=270,
    order_type=OrderType.MARKET,
    side=OrderSide.BUY,
    volume=symbol.lots_to_volume(0.1),
    relative_stop_loss=50.0,   # 50 points below entry
    relative_take_profit=100.0,  # 100 points above entry
)

result = await client.trading.place_order(account_id, request)
```

### Cancel an Order

```python
result = await client.trading.cancel_order(account_id, order_id)
print(f"Cancelled: {result.execution_type}")
```

### Close a Position

```python
from ctrader_api_client.models import ClosePositionRequest

# First, get the position to know its volume
positions = await client.trading.get_open_positions(account_id)
position = next(p for p in positions if p.position_id == position_id)

# Close the entire position
request = ClosePositionRequest(
    position_id=position.position_id,
    volume=position.volume,  # Use full volume for complete close
)

result = await client.trading.close_position(account_id, request)
print(f"Position closed: {result.execution_type}")
```

### Partial Close a Position

```python
# Get symbol to convert lots
symbol = await client.symbols.get_by_id(account_id, position.symbol_id)

# Close half of a 1-lot position
request = ClosePositionRequest(
    position_id=position.position_id,
    volume=symbol.lots_to_volume(0.5),  # Close 0.5 lots
)

result = await client.trading.close_position(account_id, request)
```

### Modify Position SL/TP

```python
from ctrader_api_client.models import AmendPositionRequest

request = AmendPositionRequest(
    position_id=123456,
    stop_loss=4900.0,
    take_profit=5200.0,
)

result = await client.trading.amend_position(account_id, request)
```

### Get Open Positions

```python
positions = await client.trading.get_open_positions(account_id)

for pos in positions:
    # Get symbol for volume conversion
    symbol = await client.symbols.get_by_id(account_id, pos.symbol_id)
    lots = symbol.volume_to_lots(pos.volume)

    print(f"Position {pos.position_id}: {lots} lots @ {pos.entry_price}")
    print(f"  Swap: {pos.swap}, Commission: {pos.commission}")
```

### Get Pending Orders

```python
orders = await client.trading.get_pending_orders(account_id)

for order in orders:
    print(f"Order {order.order_id}: {order.order_type} {order.side}")
```

### Get Historical Deals

```python
from datetime import datetime, timedelta

deals = await client.trading.get_deals(
    account_id,
    from_timestamp=datetime.now() - timedelta(days=7),
    to_timestamp=datetime.now(),
)

for deal in deals:
    print(f"Deal {deal.deal_id}: {deal.side} {deal.filled_volume}")
    print(f"  Commission: {deal.commission}")

    # Check if this deal closed a position
    if deal.is_closing_deal and deal.close_detail:
        print(f"  Gross P/L: {deal.close_detail.gross_profit}")
```
