"""Shared wiring for the connection behaviour tests."""

from __future__ import annotations

import pytest

from ctrader_api_client._internal.proto import ProtoOATraderReq, ProtoOATraderRes

from ...harness import FakeServer


@pytest.fixture
def echoing_trader(server: FakeServer) -> None:
    """The server answers trader lookups by reflecting the account back.

    Connection tests need a request that provably completes end to end, to show
    that a link is usable. What the response says is never the point, so this
    keeps the round trip out of the tests that only care about the link.
    """

    def echo(request: ProtoOATraderReq) -> ProtoOATraderRes:
        return ProtoOATraderRes(ctid_trader_account_id=request.ctid_trader_account_id)

    server.on(ProtoOATraderReq, echo)
