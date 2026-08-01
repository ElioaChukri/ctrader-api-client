"""Request/response behaviour over a real connection.

Input: bytes the server puts on the wire. Output: what the caller gets back.
"""

from __future__ import annotations

import anyio
import pytest

from ctrader_api_client import CTraderClient
from ctrader_api_client._internal.proto import (
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOATraderReq,
    ProtoOATraderRes,
)
from ctrader_api_client.exceptions import APIError, CTraderConnectionTimeoutError

from ...harness import FakeServer, factories


async def test_response_is_returned_to_the_caller(client: CTraderClient, server: FakeServer) -> None:
    server.respond(ProtoOAApplicationAuthReq, factories.app_auth_res())

    response = await client.auth.authenticate_app()

    assert isinstance(response, ProtoOAApplicationAuthRes)


async def test_request_carries_the_configured_credentials(client: CTraderClient, server: FakeServer) -> None:
    server.respond(ProtoOAApplicationAuthReq, factories.app_auth_res())

    await client.auth.authenticate_app()

    request = server.requests_of(ProtoOAApplicationAuthReq)[0]
    assert (request.client_id, request.client_secret) == ("test-client-id", "test-client-secret")


async def test_concurrent_requests_receive_their_own_responses(client: CTraderClient, server: FakeServer) -> None:
    """Responses are matched by correlation id, not by arrival order."""
    server.respond(ProtoOAApplicationAuthReq, factories.app_auth_res())
    server.on(
        ProtoOATraderReq,
        lambda request: ProtoOATraderRes(ctid_trader_account_id=request.ctid_trader_account_id),
    )
    await client.auth.authenticate_app()

    results: dict[int, int] = {}

    async def fetch(account_id: int) -> None:
        response = await client.protocol.request(ProtoOATraderReq(ctid_trader_account_id=account_id), ProtoOATraderRes)
        results[account_id] = response.ctid_trader_account_id

    async with anyio.create_task_group() as task_group:
        for account_id in (1, 2, 3, 4, 5):
            task_group.start_soon(fetch, account_id)

    assert results == {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}


async def test_out_of_order_responses_still_reach_the_right_caller(
    client: CTraderClient,
    server: FakeServer,
) -> None:
    server.silence(ProtoOATraderReq)

    results: dict[int, int] = {}

    async def fetch(account_id: int) -> None:
        response = await client.protocol.request(ProtoOATraderReq(ctid_trader_account_id=account_id), ProtoOATraderRes)
        results[account_id] = response.ctid_trader_account_id

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(fetch, 11)
        task_group.start_soon(fetch, 22)
        await server.wait_for_request(ProtoOATraderReq, count=2)

        # Answer in the reverse of the order the requests arrived.
        for entry in reversed(server.entries):
            assert isinstance(entry.message, ProtoOATraderReq)
            await server.push(
                ProtoOATraderRes(ctid_trader_account_id=entry.message.ctid_trader_account_id),
                client_msg_id=entry.client_msg_id,
            )

    assert results == {11: 11, 22: 22}


async def test_error_response_is_raised_as_api_error(client: CTraderClient, server: FakeServer) -> None:
    server.respond(
        ProtoOATraderReq,
        factories.error_res(error_code="CH_CLIENT_AUTH_FAILURE", description="bad credentials"),
    )

    with pytest.raises(APIError) as exc_info:
        await client.protocol.send_request(ProtoOATraderReq(ctid_trader_account_id=factories.ACCOUNT_ID))

    assert exc_info.value.error_code == "CH_CLIENT_AUTH_FAILURE"
    assert exc_info.value.description == "bad credentials"


async def test_silence_times_out_instead_of_hanging(client: CTraderClient, server: FakeServer) -> None:
    server.silence(ProtoOAApplicationAuthReq)

    with pytest.raises(CTraderConnectionTimeoutError):
        await client.auth.authenticate_app(timeout=0.05)
