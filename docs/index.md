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
from ctrader_api_client import AccountCredentials, ClientConfig, CTraderClient, SpotEvent

config = ClientConfig(
    client_id="your_client_id",
    client_secret="your_client_secret",
)

client = CTraderClient(config)


@client.on(SpotEvent, symbol_id=270)  # Filter by symbol
async def on_price(event: SpotEvent):
    # bid and ask are Decimals
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

## Requirements

- Python 3.12+

## License

MIT
