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

request = NewOrderRequest(
    symbol_id=270,
    order_type=OrderType.MARKET,
    side=OrderSide.BUY,
    volume=100,  # 0.01 lots (volume in cents)
)

result = await client.trading.place_order(account_id, request)
print(f"Order {result.order_id}: {result.execution_type}")
```

### Place a Limit Order

```python
request = NewOrderRequest(
    symbol_id=270,
    order_type=OrderType.LIMIT,
    side=OrderSide.BUY,
    volume=100,
    limit_price=5000.0,  # Limit price
    stop_loss=4950.0,    # Optional SL
    take_profit=5100.0,  # Optional TP
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

request = ClosePositionRequest(
    position_id=123456,
    volume=100,  # Close 0.01 lots (or full volume)
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
    print(f"Position {pos.position_id}: {pos.volume} @ {pos.entry_price}")
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
```
