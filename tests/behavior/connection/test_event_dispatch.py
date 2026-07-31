"""Delivery of server-initiated events to registered handlers."""

from __future__ import annotations

import betterproto

from ctrader_api_client import CTraderClient
from ctrader_api_client._internal.proto import (
    ProtoOAExecutionEvent,
    ProtoOASpotEvent,
    ProtoOATraderReq,
    ProtoOATraderRes,
)

from ...harness import FailingRecorder, FakeServer, Recorder, factories


async def test_event_reaches_the_handler_registered_for_its_type(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    spots: Recorder[ProtoOASpotEvent] = Recorder()
    client.protocol.on_event(ProtoOASpotEvent, spots)

    await server.push(factories.spot_event(bid=99_000, ask=99_100))
    await spots.wait_for(1)

    assert spots.only.bid == 99_000
    assert spots.only.ask == 99_100


async def test_handlers_registered_for_other_types_are_not_called(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    executions: Recorder[ProtoOAExecutionEvent] = Recorder()
    spots: Recorder[ProtoOASpotEvent] = Recorder()
    client.protocol.on_event(ProtoOAExecutionEvent, executions)
    client.protocol.on_event(ProtoOASpotEvent, spots)

    await server.push(factories.spot_event())
    await spots.wait_for(1)

    assert executions.count == 0


async def test_every_handler_for_a_type_receives_the_event(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    first: Recorder[ProtoOASpotEvent] = Recorder()
    second: Recorder[ProtoOASpotEvent] = Recorder()
    client.protocol.on_event(ProtoOASpotEvent, first)
    client.protocol.on_event(ProtoOASpotEvent, second)

    await server.push(factories.spot_event())
    await first.wait_for(1)
    await second.wait_for(1)

    assert (first.count, second.count) == (1, 1)


async def test_base_class_handler_receives_every_message(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    """Registering against `betterproto.Message` is how liveness tracking works."""
    everything: Recorder[betterproto.Message] = Recorder()
    client.protocol.on_event(betterproto.Message, everything)

    await server.push(factories.spot_event())
    await everything.wait_for(1)

    assert isinstance(everything.only, ProtoOASpotEvent)


async def test_a_failing_handler_does_not_stop_the_others(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    broken: FailingRecorder[ProtoOASpotEvent] = FailingRecorder()
    healthy: Recorder[ProtoOASpotEvent] = Recorder()
    client.protocol.on_event(ProtoOASpotEvent, broken)
    client.protocol.on_event(ProtoOASpotEvent, healthy)

    await server.push(factories.spot_event())
    await healthy.wait_for(1)

    assert healthy.count == 1


async def test_a_failing_handler_does_not_stop_later_events(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    broken: FailingRecorder[ProtoOASpotEvent] = FailingRecorder()
    client.protocol.on_event(ProtoOASpotEvent, broken)

    await server.push(factories.spot_event(bid=1))
    await broken.wait_for(1)
    await server.push(factories.spot_event(bid=2))
    await broken.wait_for(2)

    assert [event.bid for event in broken.items] == [1, 2]


async def test_removed_handlers_stop_receiving_events(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    spots: Recorder[ProtoOASpotEvent] = Recorder()
    survivor: Recorder[ProtoOASpotEvent] = Recorder()
    client.protocol.on_event(ProtoOASpotEvent, spots)
    client.protocol.on_event(ProtoOASpotEvent, survivor)

    await server.push(factories.spot_event())
    await spots.wait_for(1)

    client.protocol.remove_handler(ProtoOASpotEvent, spots)
    await server.push(factories.spot_event())
    await survivor.wait_for(2)

    assert spots.count == 1


async def test_a_response_is_not_delivered_as_an_event(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    """Correlated replies belong to their caller, not to the event stream."""
    responses: Recorder[ProtoOATraderRes] = Recorder()
    everything: Recorder[betterproto.Message] = Recorder()
    client.protocol.on_event(ProtoOATraderRes, responses)
    client.protocol.on_event(betterproto.Message, everything)
    server.respond(ProtoOATraderReq, ProtoOATraderRes())

    await client.protocol.send_request(ProtoOATraderReq(ctid_trader_account_id=1))
    await server.push(factories.spot_event())
    await everything.wait_for(1)

    assert responses.count == 0
