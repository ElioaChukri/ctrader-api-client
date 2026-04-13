# cTrader API Client

A Python client for the cTrader Open API. Provides a high-level async interface for trading operations, market data subscriptions, and account management.

## Features

- **Async/await** - Built on `anyio` for modern async Python
- **Type-safe** - Full type hints with IDE autocomplete support
- **Event-driven** - Decorator-based event handlers for real-time data
- **Automatic reconnection** - Handles connection drops with exponential backoff
- **High-level API** - Pythonic wrappers over protobuf messages

## Installation

**Using uv (recommended):**

```bash
uv add ctrader-api-client
```

**Using pip:**

```bash
pip install ctrader-api-client
```

## Quick Example

```python
import asyncio
from ctrader_api_client import CTraderClient, ClientConfig
from ctrader_api_client.events import ReadyEvent, SpotEvent

config = ClientConfig(
    client_id="your_client_id",
    client_secret="your_client_secret",
)

client = CTraderClient(config)


@client.on(SpotEvent, symbol_id=270)  # Filter by symbol
async def on_price(event: SpotEvent):
    print(f"Price update: {event.bid}/{event.ask}")


@client.on(ReadyEvent)
async def on_ready(event: ReadyEvent):
    """Called when account is authenticated and ready."""
    await client.market_data.subscribe_spots(event.account_id, [270])


async def main():
    async with client:
        await client.auth.authenticate_app()
        await client.auth.authenticate_by_trader_login(
            trader_login=12345678,
            access_token="your_access_token",
            refresh_token="your_refresh_token",
            expires_at=1778617423,
        )

        # Keep running to receive events
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
```

## Requirements

- Python 3.12+

## License

MIT
