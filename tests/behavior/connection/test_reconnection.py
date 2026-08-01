"""Reconnection behaviour after the link is lost."""

from __future__ import annotations

import logging
from collections.abc import Callable

import anyio
import pytest

from ctrader_api_client import CTraderClient
from ctrader_api_client._internal.proto import (
    ProtoOAApplicationAuthReq,
    ProtoOASpotEvent,
    ProtoOATraderReq,
    ProtoOATraderRes,
)
from ctrader_api_client.exceptions import CTraderConnectionClosedError

from ...harness import FakeServer, Recorder, factories


def _echo_trader(request: ProtoOATraderReq) -> ProtoOATraderRes:
    return ProtoOATraderRes(ctid_trader_account_id=request.ctid_trader_account_id)


async def test_client_reconnects_after_the_server_drops_the_link(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    server.respond(ProtoOAApplicationAuthReq, factories.app_auth_res())
    server.on(ProtoOATraderReq, _echo_trader)

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
    server.respond(ProtoOAApplicationAuthReq, factories.app_auth_res())

    with caplog.at_level(logging.DEBUG, logger="ctrader_api_client.connection.protocol"):
        await server.drop_connection()
        await server.wait_for_connections(2)

    message_errors = [record for record in caplog.records if "Error processing message" in record.getMessage()]

    assert message_errors == []


async def test_pending_requests_fail_fast_when_reconnection_is_disabled(
    make_client: Callable[..., CTraderClient],
    server: FakeServer,
) -> None:
    """A caller waiting on a dead connection is woken with an error, not left hanging."""
    client = make_client(reconnect_attempts=0)
    await client.connect()
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
    server: FakeServer,
) -> None:
    client = make_client(reconnect_attempts=0)
    await client.connect()

    await server.drop_connection()
    await server.wait_for_disconnect()

    with pytest.raises(CTraderConnectionClosedError):
        await client.protocol.send_request(ProtoOATraderReq(ctid_trader_account_id=1), timeout=1)


async def test_reconnection_restores_event_delivery(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    """The reader that survives a reconnect is the new one, not a stale duplicate."""
    server.respond(ProtoOAApplicationAuthReq, factories.app_auth_res())
    spots: Recorder[ProtoOASpotEvent] = Recorder()
    client.protocol.on_event(ProtoOASpotEvent, spots)

    await server.drop_connection()
    await server.wait_for_connections(2)
    await server.push(factories.spot_event(bid=111_111))
    await spots.wait_for(1)

    assert spots.count == 1
    assert spots.only.bid == 111_111
