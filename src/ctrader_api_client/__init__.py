"""cTrader Open API Python client.

A high-level async client for the cTrader trading platform.

Example:
    ```python
    import asyncio
    from ctrader_api_client import CTraderClient, ClientConfig
    from ctrader_api_client.events import SpotEvent

    config = ClientConfig(
        client_id="your_client_id",
        client_secret="your_client_secret",
    )

    client = CTraderClient(config)


    @client.on(SpotEvent, symbol_id=270)
    async def on_spot(event: SpotEvent) -> None:
        print(f"{event.bid}/{event.ask}")


    async def main():
        async with client:
            await client.auth.authenticate_app()
            creds = await client.auth.authenticate_by_trader_login(
                trader_login=17091452,
                access_token="...",
                refresh_token="...",
                expires_at=1778617423,
            )
            await client.market_data.subscribe_spots(creds.account_id, [270])
            await asyncio.Event().wait()


    asyncio.run(main())
    ```
"""

from .client import CTraderClient
from .config import ClientConfig


__all__ = [
    "CTraderClient",
    "ClientConfig",
]
