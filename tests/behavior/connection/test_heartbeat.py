"""Keep-alive behaviour, driven by a clock the test controls."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from ctrader_api_client import CTraderClient
from ctrader_api_client._internal.proto import (
    ProtoHeartbeatEvent,
    ProtoOAApplicationAuthReq,
    ProtoOASpotEvent,
)

from ...harness import FakeServer, ManualClock, Recorder, factories


INTERVAL = 5.0
TIMEOUT = 20.0

# The heartbeat loop and the token refresh loop are the two clock sleepers a
# connected client parks in; waiting for both makes advancing deterministic.
SLEEPERS_WHEN_CONNECTED = 2


@pytest.fixture
async def beating(make_client: Callable[..., CTraderClient], clock: ManualClock) -> CTraderClient:
    """A connected client with short, explicit keep-alive settings."""
    client = make_client(heartbeat_interval=INTERVAL, heartbeat_timeout=TIMEOUT)
    await client.connect()
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
    server.respond(ProtoOAApplicationAuthReq, factories.app_auth_res())

    await clock.advance(TIMEOUT + INTERVAL)

    await server.wait_for_connections(2)


async def test_server_traffic_postpones_the_timeout(
    beating: CTraderClient,
    server: FakeServer,
    clock: ManualClock,
) -> None:
    """Any message from the server counts as liveness, not just heartbeats."""
    server.respond(ProtoOAApplicationAuthReq, factories.app_auth_res())
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
    server: FakeServer,
    clock: ManualClock,
) -> None:
    client = make_client(heartbeat_interval=INTERVAL, heartbeat_timeout=0)
    await client.connect()
    await clock.wait_for_sleepers(SLEEPERS_WHEN_CONNECTED)

    await clock.advance(INTERVAL * 100)
    await server.wait_for_request(ProtoHeartbeatEvent, count=1)

    assert server.connection_count == 1
