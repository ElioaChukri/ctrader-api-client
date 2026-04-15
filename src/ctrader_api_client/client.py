from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, overload

from .api import AccountsAPI, MarketDataAPI, SymbolsAPI, TradingAPI
from .auth import AuthManager
from .config import ClientConfig
from .connection import HeartbeatManager, Protocol, Transport
from .events import (
    AccountDisconnectEvent,
    ClientDisconnectEvent,
    DepthEvent,
    Event,
    EventEmitter,
    EventRouter,
    ExecutionEvent,
    MarginCallTriggerEvent,
    MarginChangeEvent,
    OrderErrorEvent,
    PnLChangeEvent,
    ReadyEvent,
    ReconnectedEvent,
    SpotEvent,
    SymbolChangedEvent,
    TokenInvalidatedEvent,
    TraderUpdateEvent,
    TrailingStopChangedEvent,
)


logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Event)
EventHandler = Callable[[T], Awaitable[None]]

# Constrained TypeVars for overloaded on() method
# Events that support both account_id and symbol_id filters
T_BothFilters = TypeVar("T_BothFilters", SpotEvent, ExecutionEvent, DepthEvent)

# Events that support only account_id filter
T_AccountIdOnly = TypeVar(
    "T_AccountIdOnly",
    ReadyEvent,
    OrderErrorEvent,
    TraderUpdateEvent,
    MarginChangeEvent,
    AccountDisconnectEvent,
    SymbolChangedEvent,
    TrailingStopChangedEvent,
    MarginCallTriggerEvent,
    PnLChangeEvent,
)

# Events that support no filters
T_NoFilters = TypeVar(
    "T_NoFilters",
    ReconnectedEvent,
    ClientDisconnectEvent,
    TokenInvalidatedEvent,
)


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
            on_account_ready=self._emit_ready_event,
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

        # Set up reconnection handler
        self._protocol._on_reconnect = self._handle_reconnect

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
        await self._auth.start()
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

    async def _emit_ready_event(self, account_id: int, is_reconnect: bool, is_reauth: bool) -> None:
        """Emit ReadyEvent when an account is authenticated.

        Called by AuthManager after successful account authentication.

        Does NOT emit if this is a re-auth with no reconnection (e.g. token refresh), since subscriptions
        are not lost in that case and users don't need to restore them.

        Args:
            account_id: The authenticated account ID.
            is_reconnect: True if this is a re-authentication after reconnection.
        """
        if is_reauth and not is_reconnect:
            # Don't emit ReadyEvent for token refresh re-auth, since subscriptions are not lost
            return

        await self._emitter.emit(ReadyEvent(account_id=account_id, is_reconnect=is_reconnect))

    async def _handle_reconnect(self) -> None:
        """Handle automatic reconnection by re-authenticating.

        Called by Protocol after successful reconnection. Re-authenticates
        the app and all previously authenticated accounts, then emits
        a ReconnectedEvent so users can restore subscriptions.
        """
        logger.info("Connection restored, re-authenticating...")

        # Restart heartbeat monitoring
        await self._heartbeat.restart()

        restored: list[int] = []
        failed: list[tuple[int, str]] = []

        # Re-authenticate app
        try:
            await self._auth.authenticate_app()
            app_auth_restored = True
            logger.info("App re-authenticated successfully")
        except Exception as e:
            logger.error("Failed to re-authenticate app after reconnect: %s", e)
            app_auth_restored = False
            # Emit event with failure - user must handle this
            await self._emitter.emit(
                ReconnectedEvent(
                    app_auth_restored=False,
                    restored_accounts=(),
                    failed_accounts=(),
                )
            )
            return

        # Re-authenticate all previously authenticated accounts
        for account_id, credentials in list(self._auth._accounts.items()):
            try:
                await self._auth.authenticate_account(credentials, reconnect=True)
                restored.append(account_id)
                logger.info("Re-authenticated account %d", account_id)
            except Exception as e:
                logger.error("Failed to re-authenticate account %d: %s", account_id, e)
                failed.append((account_id, str(e)))

        # Emit event for user to handle subscriptions
        await self._emitter.emit(
            ReconnectedEvent(
                app_auth_restored=app_auth_restored,
                restored_accounts=tuple(restored),
                failed_accounts=tuple(failed),
            )
        )

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

    @overload
    def on(
        self,
        event_type: type[T_BothFilters],
        *,
        account_id: int | None = ...,
        symbol_id: int | None = ...,
    ) -> Callable[[EventHandler[T_BothFilters]], EventHandler[T_BothFilters]]: ...

    @overload
    def on(
        self,
        event_type: type[T_AccountIdOnly],
        *,
        account_id: int | None = ...,
    ) -> Callable[[EventHandler[T_AccountIdOnly]], EventHandler[T_AccountIdOnly]]: ...

    @overload
    def on(
        self,
        event_type: type[T_NoFilters],
    ) -> Callable[[EventHandler[T_NoFilters]], EventHandler[T_NoFilters]]: ...

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
        accounts or symbols. The event must have the corresponding account_id or symbol_id attributes
        for filtering to work. Else this will raise ValueError at registration time.

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
