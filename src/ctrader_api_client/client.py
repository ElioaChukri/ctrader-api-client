from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, TypeVar, overload

import anyio

from .api import AccountsAPI, MarketDataAPI, SymbolsAPI, TradingAPI
from .auth import AuthManager, TokenStore
from .composition import ClientGraph, build_graph
from .config import ClientConfig
from .connection import Protocol
from .events import (
    AccountDisconnectEvent,
    ClientDisconnectEvent,
    DepthEvent,
    Event,
    ExecutionEvent,
    MarginCallTriggerEvent,
    MarginChangeEvent,
    OrderErrorEvent,
    ReadyEvent,
    ReconnectedEvent,
    SpotEvent,
    SubscriptionRestoreFailedEvent,
    SymbolChangedEvent,
    TokenInvalidatedEvent,
    TokenRefreshFailedEvent,
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
    TokenRefreshFailedEvent,
    SubscriptionRestoreFailedEvent,
)

# Events that support no filters
T_NoFilters = TypeVar(
    "T_NoFilters",
    ReconnectedEvent,
    ClientDisconnectEvent,
    TokenInvalidatedEvent,
)


def _sole_failure(group: BaseExceptionGroup[BaseException]) -> BaseException:
    """The one failure a task group wrapped, or the group when there were several.

    The background tasks run in a task group, which reports even a single
    failure as a group. Callers write `except CTraderConnectionFailedError`
    around `async with client:`, not `except*`, so a lone failure is unwrapped
    on its way out. Several failures stay a group, because that is what they
    are.
    """
    failure: BaseException = group
    while isinstance(failure, BaseExceptionGroup) and len(failure.exceptions) == 1:
        failure = failure.exceptions[0]
    return failure


class CTraderClient:
    """Unified cTrader API client.

    Provides access to all API operations through namespaced interfaces
    and supports decorator-based event registration.

    Example:
        ```python
        from ctrader_api_client import CTraderClient, ClientConfig
        from ctrader_api_client.auth import AccountCredentials
        from ctrader_api_client.events import SpotEvent

        config = ClientConfig(
            client_id="your_client_id",
            client_secret="your_client_secret",
        )

        client = CTraderClient(config)


        @client.on(SpotEvent, symbol_id=270)
        async def on_price(event: SpotEvent) -> None:
            print(f"PRICE: {event.bid}/{event.ask}")


        async with client:
            account_id = await client.accounts.resolve_account_id(
                access_token="...",
                trader_login=17091452,
            )
            await client.auth.authenticate_trader(
                AccountCredentials(
                    account_id=account_id,
                    access_token="...",
                    refresh_token="...",
                    expires_at=1778617423,
                )
            )
            await client.market_data.subscribe_spots(account_id, [270])

            await asyncio.Event().wait()  # Run forever
        ```

    Attributes:
        auth: Account authentication and the sessions it produces.
        accounts: Account discovery and information operations.
        symbols: Symbol lookup and search.
        trading: Order and position operations.
        market_data: Market data subscriptions and historical data.
        protocol: Low-level protocol access for advanced usage.
    """

    def __init__(
        self,
        config: ClientConfig,
        *,
        token_store: TokenStore | None = None,
    ) -> None:
        """Initialize the client with the default object graph.

        Args:
            config: Client configuration including credentials and settings.
            token_store: Durable storage for credentials. The client writes
                through it whenever tokens rotate, but never reads it back;
                loading the stored pair at startup is the caller's job. Without
                one, refreshed tokens live only in memory.
        """
        self._adopt(build_graph(config, token_store=token_store))

    @classmethod
    def from_graph(cls, graph: ClientGraph) -> CTraderClient:
        """Build a client around a graph assembled by the caller.

        For substituting a collaborator the default assembly does not expose,
        such as a deterministic clock.

        Args:
            graph: The collaborators the client should run on.

        Returns:
            A client driving that graph.
        """
        client = cls.__new__(cls)
        client._adopt(graph)
        return client

    def _adopt(self, graph: ClientGraph) -> None:
        """Take ownership of a graph."""
        self._protocol = graph.protocol
        self._supervisor = graph.supervisor
        self._emitter = graph.emitter
        self._router = graph.router
        self._auth = graph.auth
        self._refresher = graph.refresher
        self._recovery = graph.recovery
        self._accounts = graph.accounts
        self._symbols = graph.symbols
        self._trading = graph.trading
        self._market_data = graph.market_data

        self._running: AbstractAsyncContextManager[None] | None = None

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def auth(self) -> AuthManager:
        """Authentication operations.

        The application is authenticated as the client connects, so what is
        left here is authenticating trading accounts and asking after the
        sessions they hold.
        """
        return self._auth

    @property
    def accounts(self) -> AccountsAPI:
        """Account information operations.

        Provides methods to discover the accounts an access token covers and to
        retrieve account/trader details.
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
        """Whether the client is connected to the server (transport level)."""
        return self._supervisor.is_connected

    def is_account_authorized(self, account_id: int) -> bool:
        """Whether the account currently has a live, authorized session.

        Returns False after a server-side account disconnect until recovery
        re-authentication succeeds. Distinct from is_connected, which only
        reflects the transport-level connection.

        Args:
            account_id: The cTID trader account ID.
        """
        return self._auth.is_account_authorized(account_id)

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

    @asynccontextmanager
    async def _lifecycle(self) -> AsyncIterator[None]:
        """Hold the connection and its background tasks open for the block.

        The connection layer is brought up by the supervisor, which owns the
        order it has to happen in. What is left here runs inside that: the
        application authentication that everything else depends on, and a task
        group scoped to this generator rather than handed out to the
        components, so a background loop that dies is raised here instead of
        being discovered at shutdown.
        """
        async with self._supervisor.serving():
            await self._auth.authenticate_app()
            async with anyio.create_task_group() as task_group:
                await task_group.start(self._refresher.serve)
                await task_group.start(self._recovery.serve)
                self._router.start()
                try:
                    yield
                finally:
                    logger.debug("Closing connection")
                    self._router.stop()
                    await self._recovery.stop()
                    await self._refresher.stop()

    async def __aenter__(self) -> CTraderClient:
        """Connect and authenticate the application for the life of the block.

        Returns:
            The client instance.

        Raises:
            CTraderConnectionFailedError: If connection cannot be established.
            ApplicationAuthError: If the server rejects the application credentials.
        """
        if self._running is not None:
            raise RuntimeError("Client is already connected")

        running = self._lifecycle()
        try:
            await running.__aenter__()
        except BaseExceptionGroup as group:
            failure = _sole_failure(group)
            if failure is group:
                raise
            raise failure from failure.__cause__

        self._running = running
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool | None:
        """Wind down the background tasks and close the connection."""
        running, self._running = self._running, None
        if running is None:
            return None

        try:
            return await running.__aexit__(exc_type, exc_val, exc_tb)
        except BaseExceptionGroup as group:
            failure = _sole_failure(group)
            if failure is exc_val:
                # The block's own exception, carried out through the task
                # group. Let it propagate as itself rather than re-raising it.
                return False
            if failure is group:
                raise
            raise failure from failure.__cause__

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

    @overload
    def register_handler(
        self,
        event_type: type[T_BothFilters],
        handler: EventHandler[T_BothFilters],
        *,
        account_id: int | None = ...,
        symbol_id: int | None = ...,
    ) -> None: ...

    @overload
    def register_handler(
        self,
        event_type: type[T_AccountIdOnly],
        handler: EventHandler[T_AccountIdOnly],
        *,
        account_id: int | None = ...,
    ) -> None: ...

    @overload
    def register_handler(
        self,
        event_type: type[T_NoFilters],
        handler: EventHandler[T_NoFilters],
    ) -> None: ...

    def register_handler(
        self,
        event_type: type[T],
        handler: EventHandler[T],
        *,
        account_id: int | None = None,
        symbol_id: int | None = None,
    ) -> None:
        """Register an event handler.

        Same as the on() decorator but as a regular method for dynamic registration.

        Args:
            event_type: The event class to listen for.
            handler: The async function to call when the event arrives.
            account_id: Only receive events for this account (optional).
            symbol_id: Only receive events for this symbol (optional).
        Example:
            ```python
            async def on_eurusd(event: SpotEvent) -> None:
                print(f"EURUSD: {event.bid}/{event.ask}")


            client.register_handler(SpotEvent, on_eurusd, symbol_id=270)
            ```
        """
        self._emitter.subscribe(
            event_type,
            handler,
            account_id=account_id,
            symbol_id=symbol_id,
        )

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
