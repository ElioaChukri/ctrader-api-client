"""Reconnection behaviour after the link is lost."""

from __future__ import annotations

import logging
import ssl
from collections.abc import Awaitable, Callable
from typing import Any

import anyio
import pytest

from ctrader_api_client import CTraderClient
from ctrader_api_client._internal.proto import (
    ProtoOASpotEvent,
    ProtoOATraderReq,
    ProtoOATraderRes,
)
from ctrader_api_client.composition import ClientGraph
from ctrader_api_client.config import ClientConfig
from ctrader_api_client.connection import Transport
from ctrader_api_client.exceptions import (
    CTraderConnectionClosedError,
    CTraderConnectionFailedError,
    CTraderReconnectAbandonedError,
)

from ...harness import FakeServer, Recorder, factories


# Everything a connection attempt has been seen to fail with, plus one thing it
# has not. The point of the last entry is that this list can never be complete:
# a new anyio or CPython release is free to raise something nobody here thought
# of, and the behaviour under test has to hold for that too. Tests below are
# parametrised over this rather than written per exception type, because a
# guard written against one exception is exactly what let the second outage
# through after the first was fixed.
CONNECT_FAILURES: list[Exception] = [
    # What a TLS handshake cut short by the peer actually raises. This is the
    # one that took production down: not an OSError, so it escaped translation.
    anyio.BrokenResourceError(),
    anyio.EndOfStream(),
    anyio.ClosedResourceError(),
    ssl.SSLEOFError("EOF occurred in violation of protocol"),
    ssl.SSLCertVerificationError("certificate verify failed"),
    OSError("connection refused"),
    TimeoutError("timed out"),
    RuntimeError("a failure mode nobody has predicted yet"),
]


def failing_connect(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    times: int | None = 1,
) -> None:
    """Make the next `times` connection attempts fail with `failure`.

    Patches anyio rather than `Transport.connect`, so that the transport's own
    translation of the failure is part of what is under test. `times=None`
    fails every attempt.
    """
    connect_tcp = anyio.connect_tcp
    remaining = times

    async def connect(*args: Any, **kwargs: Any) -> Any:
        nonlocal remaining
        if remaining is None:
            raise failure
        if remaining > 0:
            remaining -= 1
            raise failure
        return await connect_tcp(*args, **kwargs)

    monkeypatch.setattr(anyio, "connect_tcp", connect)


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


@pytest.mark.parametrize("failure", CONNECT_FAILURES, ids=lambda failure: type(failure).__name__)
async def test_connecting_reports_every_failure_as_a_connection_failure(
    failure: Exception,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`connect()` has two outcomes, not three: a stream, or a failure to connect.

    Regression guard: it used to translate only `OSError`, so anything else —
    `BrokenResourceError` from a broken TLS handshake, in production — came out
    as itself. Callers retry on the translated type, so an untranslated failure
    skipped the retries and was read as fatal instead.
    """
    failing_connect(monkeypatch, failure)
    transport = Transport(host="127.0.0.1", port=1, use_ssl=False)

    with pytest.raises(CTraderConnectionFailedError) as raised:
        await transport.connect()

    assert raised.value.cause is failure
    assert transport.is_connected is False


@pytest.mark.usefixtures("echoing_trader")
@pytest.mark.parametrize("failure", CONNECT_FAILURES, ids=lambda failure: type(failure).__name__)
async def test_reconnection_survives_any_failure_to_connect(
    failure: Exception,
    make_client: Callable[..., CTraderClient],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed connection attempt is a reason to try again, whatever it was.

    Regression guard for the second production outage: a `BrokenResourceError`
    from a TLS handshake the broker cut short went straight past a retry loop
    that only recognised `CTraderConnectionFailedError`, and the client died on
    attempt 1 of 5 without spending its budget. The exception type must not be
    what decides whether the client survives, so this holds for a failure no
    one has anticipated as much as for the one that happened.
    """
    client = await connected(make_client())
    failing_connect(monkeypatch, failure)

    await server.drop_connection()
    await server.wait_for_connections(2)

    response = await client.protocol.request(ProtoOATraderReq(ctid_trader_account_id=20), ProtoOATraderRes)

    assert response.ctid_trader_account_id == 20


@pytest.mark.usefixtures("echoing_trader")
async def test_reconnection_outlasts_an_outage_longer_than_the_old_budget(
    make_client: Callable[..., CTraderClient],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reconnection keeps going by default rather than running out.

    The default used to be five attempts, roughly fifteen seconds of backoff —
    less than a router reboot, after which the client was offline for good.
    Eight consecutive failures here is more than that budget would have
    survived, so this fails if the default ever becomes finite again.
    """
    client = await connected(make_client())
    failing_connect(monkeypatch, anyio.BrokenResourceError(), times=8)

    await server.drop_connection()
    await server.wait_for_connections(2)

    response = await client.protocol.request(ProtoOATraderReq(ctid_trader_account_id=21), ProtoOATraderRes)

    assert response.ctid_trader_account_id == 21


def test_reconnection_is_unbounded_unless_configured_otherwise() -> None:
    """The default is stated here so changing it has to be deliberate."""
    config = ClientConfig(client_id="id", client_secret="secret")

    assert config.reconnect_attempts is None


@pytest.mark.usefixtures("echoing_trader")
async def test_a_connection_attempt_that_hangs_is_given_up_on_and_retried(
    make_client: Callable[..., CTraderClient],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A handshake that never finishes is bounded, not waited on forever.

    The failure with no exception at all: a TLS handshake that neither
    completes nor fails leaves the reconnection parked on it, which looks
    exactly like the permanent outage a raised exception used to cause and
    leaves nothing in the log to say so.
    """
    client = await connected(make_client(connect_timeout=0.05))
    connect_tcp = anyio.connect_tcp
    hung = False

    async def connect(*args: Any, **kwargs: Any) -> Any:
        nonlocal hung
        if not hung:
            hung = True
            await anyio.sleep_forever()
        return await connect_tcp(*args, **kwargs)

    monkeypatch.setattr(anyio, "connect_tcp", connect)

    await server.drop_connection()
    await server.wait_for_connections(2)

    response = await client.protocol.request(ProtoOATraderReq(ctid_trader_account_id=22), ProtoOATraderRes)

    assert hung
    assert response.ctid_trader_account_id == 22


async def test_abandoning_reconnection_raises_out_of_the_client_block(
    make_client: Callable[..., CTraderClient],
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Giving up tears the client down instead of leaving it quietly offline.

    A client that has stopped reconnecting cannot recover on its own, so
    staying alive only means a consumer polling `is_connected` sees a link that
    is down and assumes something is working on restoring it. In production
    that assumption was logged once every few seconds for twenty-three minutes.
    """
    client = make_client(reconnect_attempts=2)

    with pytest.raises(CTraderReconnectAbandonedError) as raised:
        async with client:
            failing_connect(monkeypatch, anyio.BrokenResourceError(), times=None)
            await server.drop_connection()
            # Park until the abandonment cancels us; the deadline turns a
            # regression into a failure rather than a hung suite.
            with anyio.fail_after(10):
                await anyio.sleep_forever()

    assert isinstance(raised.value.cause, CTraderConnectionFailedError)


async def test_disabling_reconnection_does_not_tear_the_client_down(
    make_client: Callable[..., CTraderClient],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
    server: FakeServer,
) -> None:
    """Not reconnecting on request is an outcome, not a failure to report.

    The counterpart to the test above: abandonment is raised because the client
    tried and could not, which is never true when it was told not to try.
    """
    client = await connected(make_client(reconnect_attempts=0))

    await server.drop_connection()
    await server.wait_for_disconnect()

    with pytest.raises(CTraderConnectionClosedError):
        await client.protocol.send_request(ProtoOATraderReq(ctid_trader_account_id=23), timeout=1)


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
