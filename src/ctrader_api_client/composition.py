"""Assembly of the objects a client runs on.

Construction lives here rather than in `CTraderClient.__init__` so that the
wiring is stated once, in one readable place, and so that a caller who needs to
substitute a collaborator can do so without the client growing a parameter for
every seam.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._internal import Clock
from .api import AccountsAPI, MarketDataAPI, SymbolsAPI, TradingAPI
from .auth import AuthManager, SessionRecovery, SessionStore, TokenRefresher, TokenStore
from .config import ClientConfig
from .connection import ConnectionSupervisor, HeartbeatManager, Protocol, Transport
from .events import EventEmitter, EventRouter


@dataclass(frozen=True, slots=True)
class ClientGraph:
    """Every collaborator a client needs, already wired to each other.

    Attributes:
        config: The settings the graph was built from.
        transport: The TCP/SSL link.
        protocol: Framing and request/response correlation over the transport.
        heartbeat: Keeps the link alive and notices when it goes quiet.
        supervisor: Owns the three above and reports link transitions.
        emitter: The consumer-facing event bus.
        router: Translates protocol messages into events on the bus.
        auth: App and account sessions.
        refresher: Rotates access tokens before they expire.
        recovery: Re-establishes sessions the server or the link took away.
        accounts: Account information operations.
        symbols: Symbol lookup and search.
        trading: Order and position operations.
        market_data: Market data subscriptions and historical data.
    """

    config: ClientConfig
    transport: Transport
    protocol: Protocol
    heartbeat: HeartbeatManager
    supervisor: ConnectionSupervisor
    emitter: EventEmitter
    router: EventRouter
    auth: AuthManager
    refresher: TokenRefresher
    recovery: SessionRecovery
    accounts: AccountsAPI
    symbols: SymbolsAPI
    trading: TradingAPI
    market_data: MarketDataAPI


def build_graph(
    config: ClientConfig,
    *,
    token_store: TokenStore | None = None,
    clock: Clock | None = None,
) -> ClientGraph:
    """Assemble the default object graph from configuration.

    Args:
        config: Client configuration including credentials and settings.
        token_store: Durable storage for rotated credentials. Without one,
            refreshed tokens live only in memory and are lost on restart.
        clock: Time source for the heartbeat and token-refresh timers. Defaults
            to real monotonic time; pass a deterministic one to drive those
            timers from a test.

    Returns:
        The assembled graph, ready to hand to `CTraderClient.from_graph`.
    """
    transport = Transport(
        host=config.host,
        port=config.port,
        use_ssl=config.use_ssl,
    )
    protocol = Protocol(
        transport=transport,
        reconnect_attempts=config.reconnect_attempts,
        reconnect_min_wait=config.reconnect_min_wait,
        reconnect_max_wait=config.reconnect_max_wait,
    )
    heartbeat = HeartbeatManager(
        protocol=protocol,
        interval=config.heartbeat_interval,
        timeout=config.heartbeat_timeout,
        clock=clock,
    )
    supervisor = ConnectionSupervisor(
        transport=transport,
        protocol=protocol,
        heartbeat=heartbeat,
    )

    emitter = EventEmitter()

    # Built before the auth manager, which asks it to restore subscriptions
    # onto each re-established session.
    market_data = MarketDataAPI(
        protocol=protocol,
        publisher=emitter,
        default_timeout=config.request_timeout,
    )

    # Shared by the three parties that between them keep sessions alive.
    sessions = SessionStore()

    auth = AuthManager(
        protocol=protocol,
        publisher=emitter,
        client_id=config.client_id,
        client_secret=config.client_secret,
        store=sessions,
        restorer=market_data,
    )

    refresher = TokenRefresher(
        protocol=protocol,
        store=sessions,
        authenticator=auth,
        publisher=emitter,
        policy=config.refresh_policy,
        clock=clock,
        token_store=token_store,
    )

    recovery = SessionRecovery(
        store=sessions,
        authenticator=auth,
        publisher=emitter,
        policy=config.reauth_policy,
        clock=clock,
    )

    router = EventRouter(
        protocol=protocol,
        emitter=emitter,
        recovery=recovery,
    )

    # The sessions live on the far side of the link, so recovery is the party
    # that has to hear about it going down and coming back.
    supervisor.add_listener(recovery)

    return ClientGraph(
        config=config,
        transport=transport,
        protocol=protocol,
        heartbeat=heartbeat,
        supervisor=supervisor,
        emitter=emitter,
        router=router,
        auth=auth,
        refresher=refresher,
        recovery=recovery,
        accounts=AccountsAPI(protocol=protocol, default_timeout=config.request_timeout),
        symbols=SymbolsAPI(protocol=protocol, default_timeout=config.request_timeout),
        trading=TradingAPI(protocol=protocol, default_timeout=config.request_timeout),
        market_data=market_data,
    )
