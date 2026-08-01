"""How the client reacts to malformed traffic on a live connection."""

from __future__ import annotations

import logging
import struct

import pytest

from ctrader_api_client import CTraderClient
from ctrader_api_client._internal.proto import (
    ProtoOAApplicationAuthReq,
    ProtoOASpotEvent,
    ProtoOATraderReq,
    ProtoOATraderRes,
)

from ...harness import FakeServer, Recorder, encode_frame, encode_message_frame, factories


_ONE_MEGABYTE = 1024 * 1024


def _echo_trader(request: ProtoOATraderReq) -> ProtoOATraderRes:
    return ProtoOATraderRes(ctid_trader_account_id=request.ctid_trader_account_id)


async def test_oversized_frame_resets_the_connection(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    """An impossible length prefix means the stream is desynchronised; reconnect."""
    server.respond(ProtoOAApplicationAuthReq, factories.app_auth_res())

    await server.send_raw(struct.pack(">I", _ONE_MEGABYTE + 1))
    await server.wait_for_connections(2)

    server.on(ProtoOATraderReq, _echo_trader)
    response = await client.protocol.request(ProtoOATraderReq(ctid_trader_account_id=3), ProtoOATraderRes)

    assert response.ctid_trader_account_id == 3


async def test_undecodable_payload_does_not_kill_the_connection(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    """One bad message is skipped; the connection keeps serving later traffic."""
    server.on(ProtoOATraderReq, _echo_trader)

    await server.send_raw(struct.pack(">I", 5) + b"\xff\xff\xff\xff\xff")
    response = await client.protocol.request(ProtoOATraderReq(ctid_trader_account_id=4), ProtoOATraderRes)

    assert response.ctid_trader_account_id == 4
    assert server.connection_count == 1


async def test_unknown_payload_type_does_not_kill_the_connection(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    server.on(ProtoOATraderReq, _echo_trader)

    await server.send_raw(encode_frame(payload_type=64999, payload=b""))
    response = await client.protocol.request(ProtoOATraderReq(ctid_trader_account_id=5), ProtoOATraderRes)

    assert response.ctid_trader_account_id == 5
    assert server.connection_count == 1


async def test_a_single_bad_message_is_logged_once(
    client: CTraderClient,
    server: FakeServer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The error path must not retry the same failure in a loop."""
    server.on(ProtoOATraderReq, _echo_trader)

    with caplog.at_level(logging.WARNING, logger="ctrader_api_client.connection.protocol"):
        await server.send_raw(struct.pack(">I", 5) + b"\xff\xff\xff\xff\xff")
        await client.protocol.send_request(ProtoOATraderReq(ctid_trader_account_id=6))

    failures = [record for record in caplog.records if "Error processing message" in record.getMessage()]

    assert len(failures) == 1


async def test_message_split_across_packets_is_reassembled(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    spots: Recorder[ProtoOASpotEvent] = Recorder()
    client.protocol.on_event(ProtoOASpotEvent, spots)
    frame = encode_message_frame(factories.spot_event(bid=123_456))

    for index in range(len(frame)):
        await server.send_raw(frame[index : index + 1])

    await spots.wait_for(1)

    assert spots.only.bid == 123_456


async def test_two_messages_in_one_packet_are_both_delivered(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    spots: Recorder[ProtoOASpotEvent] = Recorder()
    client.protocol.on_event(ProtoOASpotEvent, spots)

    first = encode_message_frame(factories.spot_event(bid=1))
    second = encode_message_frame(factories.spot_event(bid=2))
    await server.send_raw(first + second)
    await spots.wait_for(2)

    assert [event.bid for event in spots.items] == [1, 2]
