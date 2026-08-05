"""Keep-alive behaviour, driven by a clock the test controls."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import anyio
import pytest

from ctrader_api_client import CTraderClient
from ctrader_api_client._internal.proto import (
    ProtoHeartbeatEvent,
    ProtoOASpotEvent,
)
from ctrader_api_client.connection import HeartbeatManager

from ...harness import FakeServer, ManualClock, Recorder, StubProtocol, factories


INTERVAL = 5.0
TIMEOUT = 20.0

# The heartbeat loop and the token refresh loop are the two clock sleepers a
# connected client parks in; waiting for both makes advancing deterministic.
SLEEPERS_WHEN_CONNECTED = 2


@pytest.fixture
async def beating(
    make_client: Callable[..., CTraderClient],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
    clock: ManualClock,
) -> CTraderClient:
    """A connected client with short, explicit keep-alive settings."""
    client = await connected(make_client(heartbeat_interval=INTERVAL, heartbeat_timeout=TIMEOUT))
    await clock.wait_for_sleepers(SLEEPERS_WHEN_CONNECTED)
    return client


@pytest.mark.usefixtures("beating")
async def test_heartbeat_is_sent_once_per_interval(server: FakeServer, clock: ManualClock) -> None:
    await clock.advance(INTERVAL)
    await server.wait_for_request(ProtoHeartbeatEvent, count=1)

    await clock.wait_for_sleepers(SLEEPERS_WHEN_CONNECTED)
    await clock.advance(INTERVAL)
    await server.wait_for_request(ProtoHeartbeatEvent, count=2)

    assert len(server.requests_of(ProtoHeartbeatEvent)) == 2


@pytest.mark.usefixtures("beating")
async def test_no_heartbeat_before_the_interval_elapses(server: FakeServer, clock: ManualClock) -> None:
    await clock.advance(INTERVAL / 2)

    assert server.requests_of(ProtoHeartbeatEvent) == []


@pytest.mark.usefixtures("beating")
async def test_silence_beyond_the_timeout_reconnects(server: FakeServer, clock: ManualClock) -> None:
    await clock.advance(TIMEOUT + INTERVAL)

    await server.wait_for_connections(2)


async def test_server_traffic_postpones_the_timeout(
    beating: CTraderClient,
    server: FakeServer,
    clock: ManualClock,
) -> None:
    """Any message from the server counts as liveness, not just heartbeats."""
    spots: Recorder[ProtoOASpotEvent] = Recorder()
    beating.protocol.on_event(ProtoOASpotEvent, spots)
    most_of_the_timeout = TIMEOUT * 0.75

    await clock.advance(most_of_the_timeout)
    await server.wait_for_request(ProtoHeartbeatEvent, count=1)

    await server.push(factories.spot_event())
    await spots.wait_for(1)
    await clock.wait_for_sleepers(SLEEPERS_WHEN_CONNECTED)
    await clock.advance(most_of_the_timeout)
    await server.wait_for_request(ProtoHeartbeatEvent, count=2)

    assert server.connection_count == 1


async def test_timeout_can_be_disabled(
    make_client: Callable[..., CTraderClient],
    connected: Callable[[CTraderClient], Awaitable[CTraderClient]],
    server: FakeServer,
    clock: ManualClock,
) -> None:
    await connected(make_client(heartbeat_interval=INTERVAL, heartbeat_timeout=0))
    await clock.wait_for_sleepers(SLEEPERS_WHEN_CONNECTED)

    await clock.advance(INTERVAL * 100)
    await server.wait_for_request(ProtoHeartbeatEvent, count=1)

    assert server.connection_count == 1


async def test_serving_a_running_monitor_again_is_refused(
    clock: ManualClock,
    serving: Callable[[HeartbeatManager], None],
) -> None:
    """A second loop would be orphaned by the first, so stop() could never reach it."""
    heartbeat = HeartbeatManager(protocol=StubProtocol(), interval=INTERVAL, timeout=TIMEOUT, clock=clock)
    serving(heartbeat)
    await clock.wait_for_sleepers(1)

    with pytest.raises(RuntimeError):
        await heartbeat.serve()

    assert clock.sleeper_count == 1


async def test_a_stopped_monitor_stops_tracking_activity(clock: ManualClock) -> None:
    """Handlers outliving the loop would keep resetting a timer nobody reads."""
    protocol = StubProtocol()
    heartbeat = HeartbeatManager(protocol=protocol, interval=INTERVAL, timeout=TIMEOUT, clock=clock)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(heartbeat.serve)
        await clock.wait_for_sleepers(1)
        assert protocol.handler_count > 0
        await heartbeat.stop()

    assert protocol.handler_count == 0
    assert protocol.sent_of(ProtoHeartbeatEvent) == []
