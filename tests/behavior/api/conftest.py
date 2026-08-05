"""API namespaces wired to a scripted protocol."""

from __future__ import annotations

import pytest

from ctrader_api_client.api import AccountsAPI, MarketDataAPI, SymbolsAPI, TradingAPI

from ...harness import RecordingPublisher, StubProtocol


@pytest.fixture
def publisher() -> RecordingPublisher:
    return RecordingPublisher()


@pytest.fixture
def accounts(protocol: StubProtocol) -> AccountsAPI:
    return AccountsAPI(protocol=protocol)


@pytest.fixture
def symbols(protocol: StubProtocol) -> SymbolsAPI:
    return SymbolsAPI(protocol=protocol)


@pytest.fixture
def trading(protocol: StubProtocol) -> TradingAPI:
    return TradingAPI(protocol=protocol)


@pytest.fixture
def market_data(protocol: StubProtocol, publisher: RecordingPublisher) -> MarketDataAPI:
    return MarketDataAPI(protocol=protocol, publisher=publisher)
