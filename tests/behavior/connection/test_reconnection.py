"""Reconnection behaviour after the link is lost."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

import anyio
import pytest

from ctrader_api_client import CTraderClient
from ctrader_api_client._internal.proto import (
    ProtoOASpotEvent,
    ProtoOATraderReq,
    ProtoOATraderRes,
)
from ctrader_api_client.composition import ClientGraph
from ctrader_api_client.connection import Transport
from ctrader_api_client.exceptions import CTraderConnectionClosedError

from ...harness import FakeServer, Recorder, factories


@pytest.mark.usefixtures("echoing_trader")
async def test_client_reconnects_after_the_server_drops_the_link(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    await server.drop_connection()
    await server.wait_for_connections(2)

    response = await client.protocol.request(ProtoOATraderReq(ctid_trader_account_id=7), ProtoOATraderRes)

    assert response.ctid_trader_account_id == 7


@pytest.mark.usefixtures("client")
async def test_reconnection_does_not_log_per_message_errors(
    server: FakeServer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A lost link is a connection event, not a stream of message failures.

    Regression guard: the reader loop used to treat connection-level failures
    as per-message errors and retry them without ever suspending, emitting
    thousands of identical warnings per second and pinning a core.
    """
    with caplog.at_level(logging.DEBUG, logger="ctrader_api_client.connection.protocol"):
        await server.drop_connection()
        await server.wait_for_connections(2)

    message_errors = [record for record in caplog.records if "Error processing message" in record.getMessage()]

    assert message_errors == []


async def test_pending_requests_fail_fast_when_reconnection_is_disabled(
    make_client: Callable[..., CTraderClient],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
    server: FakeServer,
) -> None:
    """A caller waiting on a dead connection is woken with an error, not left hanging."""
    client = await connected(make_client(reconnect_attempts=0))
    server.silence(ProtoOATraderReq)

    failures: list[Exception] = []

    async def request() -> None:
        try:
            await client.protocol.send_request(ProtoOATraderReq(ctid_trader_account_id=1), timeout=10)
        except Exception as error:  # noqa: BLE001 - the type is the assertion
            failures.append(error)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(request)
        await server.wait_for_request(ProtoOATraderReq)
        await server.drop_connection()

    assert isinstance(failures[0], CTraderConnectionClosedError)


async def test_requests_after_failed_reconnection_are_rejected(
    make_client: Callable[..., CTraderClient],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
    server: FakeServer,
) -> None:
    client = await connected(make_client(reconnect_attempts=0))

    await server.drop_connection()
    await server.wait_for_disconnect()

    with pytest.raises(CTraderConnectionClosedError):
        await client.protocol.send_request(ProtoOATraderReq(ctid_trader_account_id=1), timeout=1)


async def test_reconnection_restores_event_delivery(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    """The reader that survives a reconnect is the new one, not a stale duplicate."""
    spots: Recorder[ProtoOASpotEvent] = Recorder()
    client.protocol.on_event(ProtoOASpotEvent, spots)

    await server.drop_connection()
    await server.wait_for_connections(2)
    await server.push(factories.spot_event(bid=111_111))
    await spots.wait_for(1)

    assert spots.count == 1
    assert spots.only.bid == 111_111


async def test_closing_a_transport_whose_socket_is_broken_does_not_raise() -> None:
    """A socket that refuses a graceful shutdown is still going away.

    A broken TLS session raises `BrokenResourceError` out of `aclose()`, because
    the close-notify it tries to write cannot be sent. That is the expected
    ending for a link that is already dead, not a failure to report.
    """
    transport = Transport(host="stub.invalid", port=0, use_ssl=False)

    class BrokenStream:
        async def aclose(self) -> None:
            raise anyio.BrokenResourceError

    transport._stream = BrokenStream()  # type: ignore[assignment]  # noqa: SLF001 - no public seam for a broken stream

    await transport.close()

    assert transport.is_connected is False


@pytest.mark.usefixtures("echoing_trader")
async def test_reconnection_survives_a_transport_that_cannot_be_closed(
    make_graph: Callable[..., ClientGraph],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
    server: FakeServer,
) -> None:
    """Failing to tear down the dead link must not abandon the reconnection.

    Regression guard: closing the old transport is the first thing a
    reconnection does, and on an already-broken socket that close can raise.
    The exception used to be indistinguishable from an exhausted retry loop, so
    the client stopped reconnecting permanently — while never having attempted
    a single reconnection on that cycle.
    """
    graph = make_graph()
    close_cleanly = graph.transport.close
    refusals = [anyio.BrokenResourceError()]

    async def close_raising_once() -> None:
        # Raise *after* the real teardown, the way the broken socket did: the
        # stream is released first, and only the graceful TLS shutdown fails.
        await close_cleanly()
        if refusals:
            raise refusals.pop()

    graph.transport.close = close_raising_once  # type: ignore[method-assign]
    client = await connected(CTraderClient.from_graph(graph))

    await server.drop_connection()
    await server.wait_for_connections(2)

    response = await client.protocol.request(ProtoOATraderReq(ctid_trader_account_id=10), ProtoOATraderRes)

    assert response.ctid_trader_account_id == 10


@pytest.mark.usefixtures("echoing_trader")
async def test_a_drop_reported_while_reconnecting_is_not_lost(
    make_graph: Callable[..., ClientGraph],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
    server: FakeServer,
) -> None:
    """A drop reported mid-reconnection is acted on, not silently swallowed.

    This is the only window in which nothing else can pick the report up: a
    detector is refused while a reconnection is in flight, and the reader loop
    exits as soon as it has reported, so the reconnection already running has to
    go round again on its behalf. The report is made from a listener, which runs
    inside that window by construction, and the link is left healthy so that no
    *other* detector can mask the loss by noticing independently.
    """
    graph = make_graph()

    class ReportsADropWhileTheReconnectionIsInFlight:
        def __init__(self) -> None:
            self.reported = False

        async def on_connection_lost(self) -> None: ...

        async def on_connection_restored(self) -> None:
            if self.reported:
                return
            self.reported = True
            await graph.protocol.handle_disconnect()

    graph.supervisor.add_listener(ReportsADropWhileTheReconnectionIsInFlight())
    client = await connected(CTraderClient.from_graph(graph))

    await server.drop_connection()
    await server.wait_for_connections(3)

    response = await client.protocol.request(ProtoOATraderReq(ctid_trader_account_id=12), ProtoOATraderRes)

    assert response.ctid_trader_account_id == 12


@pytest.mark.usefixtures("echoing_trader")
async def test_a_failing_listener_does_not_block_reconnection(
    make_graph: Callable[..., ClientGraph],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
    server: FakeServer,
) -> None:
    """A listener that raises on the drop must not stop the client from reconnecting."""

    class FailsOnLoss:
        async def on_connection_lost(self) -> None:
            raise RuntimeError("listener failed on disconnect")

        async def on_connection_restored(self) -> None: ...

    graph = make_graph()
    graph.supervisor.add_listener(FailsOnLoss())
    client = await connected(CTraderClient.from_graph(graph))

    await server.drop_connection()
    await server.wait_for_connections(2)

    response = await client.protocol.request(ProtoOATraderReq(ctid_trader_account_id=8), ProtoOATraderRes)

    assert response.ctid_trader_account_id == 8


@pytest.mark.usefixtures("echoing_trader")
async def test_a_failing_listener_does_not_leave_the_client_unusable(
    make_graph: Callable[..., ClientGraph],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
    server: FakeServer,
) -> None:
    """A listener that raises once the link is back must not undo the reconnection."""

    class FailsOnRestore:
        async def on_connection_lost(self) -> None: ...

        async def on_connection_restored(self) -> None:
            raise RuntimeError("listener failed on reconnect")

    graph = make_graph()
    graph.supervisor.add_listener(FailsOnRestore())
    client = await connected(CTraderClient.from_graph(graph))

    await server.drop_connection()
    await server.wait_for_connections(2)

    response = await client.protocol.request(ProtoOATraderReq(ctid_trader_account_id=9), ProtoOATraderRes)

    assert response.ctid_trader_account_id == 9
