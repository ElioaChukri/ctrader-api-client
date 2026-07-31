"""Shared fixtures for the whole suite.

Everything reusable lives here or in `tests/harness`, so individual tests stay
about behaviour rather than setup, and so waiting is always done on an
observable condition rather than a sleep.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import pytest

from ctrader_api_client import CTraderClient
from ctrader_api_client.config import ClientConfig

from .harness import FakeServer, ManualClock, StubProtocol


@pytest.fixture
def anyio_backend() -> str:
    """Run every async test on asyncio; the library supports no other backend in practice."""
    return "asyncio"


@pytest.fixture
def clock() -> ManualClock:
    """A clock that only moves when the test says so."""
    return ManualClock()


@pytest.fixture
def protocol() -> StubProtocol:
    """A protocol whose responses are scripted by the test."""
    return StubProtocol()


@pytest.fixture
async def server() -> AsyncIterator[FakeServer]:
    """A cTrader server listening on an ephemeral loopback port."""
    async with FakeServer() as fake_server:
        yield fake_server


@pytest.fixture
def make_config(server: FakeServer) -> Callable[..., ClientConfig]:
    """Build a client config pointed at the fake server.

    Reconnection waits are collapsed to near-zero: backoff is driven by
    tenacity rather than the injected clock, so leaving the defaults would make
    reconnection tests slow rather than deterministic.
    """

    def factory(**overrides: object) -> ClientConfig:
        settings: dict[str, object] = {
            "host": "127.0.0.1",
            "port": server.port,
            "use_ssl": False,
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "request_timeout": 5.0,
            "reconnect_min_wait": 0.001,
            "reconnect_max_wait": 0.01,
        }
        settings.update(overrides)
        return ClientConfig(**settings)  # type: ignore[arg-type]

    return factory


@pytest.fixture
async def make_client(
    make_config: Callable[..., ClientConfig],
    clock: ManualClock,
) -> AsyncIterator[Callable[..., CTraderClient]]:
    """Build clients wired to the fake server and the manual clock.

    Any client built through this factory is closed when the test ends, so a
    failing assertion cannot leave a reader loop running into the next test.
    """
    clients: list[CTraderClient] = []

    def factory(**overrides: object) -> CTraderClient:
        client = CTraderClient(make_config(**overrides), _clock=clock)
        clients.append(client)
        return client

    yield factory

    for client in clients:
        await client.close()


@pytest.fixture
async def client(make_client: Callable[..., CTraderClient]) -> AsyncIterator[CTraderClient]:
    """A client already connected to the fake server."""
    connected = make_client()
    await connected.connect()
    try:
        yield connected
    finally:
        await connected.close()
