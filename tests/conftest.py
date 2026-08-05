"""Shared fixtures for the whole suite.

Everything reusable lives here or in `tests/harness`, so individual tests stay
about behaviour rather than setup, and so waiting is always done on an
observable condition rather than a sleep.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from typing import Protocol as TypingProtocol

import anyio
import anyio.abc
import pytest

from ctrader_api_client import CTraderClient
from ctrader_api_client._internal.proto import ProtoOAApplicationAuthReq
from ctrader_api_client.composition import ClientGraph, build_graph
from ctrader_api_client.config import ClientConfig

from .harness import FakeServer, ManualClock, StubProtocol, factories


class Servable(TypingProtocol):
    """A component whose background loops are run by whoever owns them."""

    async def serve(self, *, task_status: anyio.abc.TaskStatus[None] = ...) -> None:
        """Run until stopped or cancelled, reporting when it is live."""
        ...


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
    """A cTrader server listening on an ephemeral loopback port.

    Application authentication is answered out of the box, because connecting a
    client now depends on it; a test that cares about that exchange scripts it
    again for itself.
    """
    async with FakeServer() as fake_server:
        fake_server.respond(ProtoOAApplicationAuthReq, factories.app_auth_res())
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
async def serving() -> AsyncIterator[Callable[[Servable], None]]:
    """Run a component's background loops for the rest of the test.

    The task group lives here rather than in the component, so a loop that dies
    surfaces at the end of the test instead of being swallowed. Spawning does
    not wait for the loops to be live; tests already synchronise on an
    observable condition such as the component parking on the clock.
    """
    async with anyio.create_task_group() as task_group:

        def start(component: Servable) -> None:
            task_group.start_soon(component.serve)

        yield start
        task_group.cancel_scope.cancel()


@pytest.fixture
def make_graph(
    make_config: Callable[..., ClientConfig],
    clock: ManualClock,
) -> Callable[..., ClientGraph]:
    """Build the graph a client runs on, wired to the fake server and manual clock.

    Tests that need to reach a collaborator the client does not expose, such as
    the connection supervisor, take the graph and hand it to `from_graph`.
    """

    def factory(**overrides: object) -> ClientGraph:
        return build_graph(make_config(**overrides), clock=clock)

    return factory


@pytest.fixture
def make_client(make_graph: Callable[..., ClientGraph]) -> Callable[..., CTraderClient]:
    """Build clients wired to the fake server and the manual clock.

    The client is not connected; use the `connected` fixture to bring one up.
    """

    def factory(**overrides: object) -> CTraderClient:
        return CTraderClient.from_graph(make_graph(**overrides))

    return factory


@pytest.fixture
async def connected() -> AsyncIterator[Callable[[CTraderClient], Awaitable[CTraderClient]]]:
    """Bring clients up for the rest of the test.

    Every client entered through this is wound down when the test ends, so a
    failing assertion cannot leave a reader loop running into the next test.
    """
    async with AsyncExitStack() as stack:

        async def enter(client: CTraderClient) -> CTraderClient:
            return await stack.enter_async_context(client)

        yield enter


@pytest.fixture
async def client(
    make_client: Callable[..., CTraderClient],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
) -> CTraderClient:
    """A client already connected to the fake server."""
    return await connected(make_client())
