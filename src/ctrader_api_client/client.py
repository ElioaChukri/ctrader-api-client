from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from .api import AccountsAPI, MarketDataAPI, SymbolsAPI, TradingAPI
from .auth import AuthManager
from .config import ClientConfig
from .connection import HeartbeatManager, Protocol, Transport
from .events import Event, EventEmitter, EventRouter


logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Event)
EventHandler = Callable[[T], Awaitable[None]]


class CTraderClient:
    """Unified cTrader API client.

    Provides access to all API operations through namespaced interfaces
    and supports decorator-based event registration.

    Example:
        ```python
        from ctrader_api_client import CTraderClient, ClientConfig
        from ctrader_api_client.events import SpotEvent

        config = ClientConfig(
            client_id="your_client_id",
            client_secret="your_client_secret",
        )

        client = CTraderClient(config)


        @client.on(SpotEvent, symbol_id=270)
        async def on_eurusd(event: SpotEvent) -> None:
            print(f"EURUSD: {event.bid}/{event.ask}")


        async with client:
            await client.auth.authenticate_app()
            creds = await client.auth.authenticate_by_trader_login(
                trader_login=17091452,
                access_token="...",
                refresh_token="...",
                expires_at=1778617423,
            )
            await client.market_data.subscribe_spots(creds.account_id, [270])

            await asyncio.Event().wait()  # Run forever
        ```

    Attributes:
        auth: Authentication operations (app auth, account auth, token refresh).
        accounts: Account information operations.
        symbols: Symbol lookup and search.
        trading: Order and position operations.
        market_data: Market data subscriptions and historical data.
        protocol: Low-level protocol access for advanced usage.
    """

    def __init__(self, config: ClientConfig) -> None:
        """Initialize the client.

        Args:
            config: Client configuration including credentials and settings.
        """
        self._config = config

        # Connection layer
        self._transport = Transport(
            host=config.host,
            port=config.port,
            use_ssl=config.use_ssl,
        )
        self._protocol = Protocol(
            transport=self._transport,
            reconnect_attempts=config.reconnect_attempts,
            reconnect_min_wait=config.reconnect_min_wait,
            reconnect_max_wait=config.reconnect_max_wait,
        )
        self._heartbeat = HeartbeatManager(
            protocol=self._protocol,
            interval=config.heartbeat_interval,
            timeout=config.heartbeat_timeout,
        )

        # Event system
        self._emitter = EventEmitter()
        self._router = EventRouter(
            protocol=self._protocol,
            emitter=self._emitter,
        )

        # Auth manager
        self._auth = AuthManager(
            protocol=self._protocol,
            client_id=config.client_id,
            client_secret=config.client_secret,
        )

        # API namespaces
        self._accounts = AccountsAPI(
            protocol=self._protocol,
            default_timeout=config.request_timeout,
        )
        self._symbols = SymbolsAPI(
            protocol=self._protocol,
            default_timeout=config.request_timeout,
        )
        self._trading = TradingAPI(
            protocol=self._protocol,
            default_timeout=config.request_timeout,
        )
        self._market_data = MarketDataAPI(
            protocol=self._protocol,
            default_timeout=config.request_timeout,
        )

        self._connected = False

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def auth(self) -> AuthManager:
        """Authentication operations.

        Provides methods for:
        - Application authentication
        - Account authentication
        - Token refresh management
        - Account discovery
        """
        return self._auth

    @property
    def accounts(self) -> AccountsAPI:
        """Account information operations.

        Provides methods to retrieve account/trader details.
        """
        return self._accounts

    @property
    def symbols(self) -> SymbolsAPI:
        """Symbol lookup and search.

        Provides methods to list, retrieve, and search trading symbols.
        """
        return self._symbols

    @property
    def trading(self) -> TradingAPI:
        """Order and position operations.

        Provides methods for:
        - Placing orders (market, limit, stop)
        - Modifying orders
        - Canceling orders
        - Closing positions
        - Querying positions and orders
        """
        return self._trading

    @property
    def market_data(self) -> MarketDataAPI:
        """Market data subscriptions and historical data.

        Provides methods for:
        - Subscribing to spot prices
        - Subscribing to trendbars (candles)
        - Subscribing to depth of market
        - Retrieving historical data
        """
        return self._market_data

    @property
    def is_connected(self) -> bool:
        """Whether the client is connected to the server."""
        return self._connected and self._transport.is_connected

    @property
    def protocol(self) -> Protocol:
        """Direct access to the protocol layer.

        For advanced usage when you need to send raw protobuf messages
        or handle responses not covered by the high-level API.
        """
        return self._protocol

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect to the cTrader server.

        Establishes the TCP/SSL connection, starts the protocol reader,
        heartbeat monitor, and event router.

        Raises:
            CTraderConnectionFailedError: If connection cannot be established.
        """
        if self._connected:
            return

        logger.info("Connecting to %s:%d", self._config.host, self._config.port)

        await self._transport.connect()
        await self._protocol.start()
        await self._heartbeat.start()
        self._router.start()

        self._connected = True
        logger.info("Connected successfully")

    async def close(self) -> None:
        """Close the connection and clean up resources.

        Stops the event router, heartbeat monitor, protocol reader,
        and closes the transport.
        """
        if not self._connected:
            return

        logger.info("Closing connection")

        self._router.stop()
        await self._auth.stop()
        await self._heartbeat.stop()
        await self._protocol.stop()
        await self._transport.close()

        self._connected = False
        logger.info("Connection closed")

    async def __aenter__(self) -> CTraderClient:
        """Async context manager entry.

        Connects to the server automatically.

        Returns:
            The client instance.
        """
        await self.connect()
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: Any,
    ) -> None:
        """Async context manager exit.

        Closes the connection automatically.
        """
        await self.close()

    # -------------------------------------------------------------------------
    # Event Registration
    # -------------------------------------------------------------------------

    def on(
        self,
        event_type: type[T],
        *,
        account_id: int | None = None,
        symbol_id: int | None = None,
    ) -> Callable[[EventHandler[T]], EventHandler[T]]:
        """Decorator to register an event handler.

        Handlers are called when events of the specified type arrive.
        Optional filters can be used to only receive events for specific
        accounts or symbols.
        It is advised to specify at least one filter since handlers
        are called sequentially. Subscribing a large number of handlers with no
        filters means they are all called sequentially, and handlers registered last
        will potentially fire off much later than other ones.

        Args:
            event_type: The event class to listen for.
            account_id: Only receive events for this account (optional).
            symbol_id: Only receive events for this symbol (optional).

        Returns:
            Decorator function that registers the handler.

        Example:
            ```python
            @client.on(SpotEvent, symbol_id=270)
            async def on_eurusd(event: SpotEvent) -> None:
                print(f"EURUSD: {event.bid}/{event.ask}")


            @client.on(ExecutionEvent)
            async def on_execution(event: ExecutionEvent) -> None:
                print(f"Order {event.order_id}: {event.execution_type}")
            ```
        """

        def decorator(handler: EventHandler[T]) -> EventHandler[T]:
            self._emitter.subscribe(
                event_type,
                handler,
                account_id=account_id,
                symbol_id=symbol_id,
            )
            return handler

        return decorator

    def off(
        self,
        event_type: type[T],
        handler: EventHandler[T],
    ) -> bool:
        """Unregister an event handler.

        Args:
            event_type: The event class.
            handler: The handler function to remove.

        Returns:
            True if handler was found and removed, False otherwise.

        Example:
            ```python
            @client.on(SpotEvent)
            async def handler(event: SpotEvent) -> None: ...


            # Later, unregister
            client.off(SpotEvent, handler)
            ```
        """
        return self._emitter.unsubscribe(event_type, handler)
