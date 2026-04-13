"""Tests for CTraderClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ctrader_api_client import ClientConfig, CTraderClient
from ctrader_api_client.api import AccountsAPI, MarketDataAPI, SymbolsAPI, TradingAPI
from ctrader_api_client.auth import AuthManager
from ctrader_api_client.connection import HeartbeatManager, Protocol, Transport
from ctrader_api_client.events import EventEmitter, EventRouter, SpotEvent


@pytest.fixture
def config() -> ClientConfig:
    """Create a test configuration."""
    return ClientConfig(
        host="test.ctraderapi.com",
        port=5035,
        use_ssl=True,
        client_id="test_client_id",
        client_secret="test_client_secret",
        heartbeat_interval=15.0,
        heartbeat_timeout=45.0,
        request_timeout=60.0,
        reconnect_attempts=3,
        reconnect_min_wait=2.0,
        reconnect_max_wait=30.0,
    )


class TestCTraderClientInit:
    """Test CTraderClient initialization."""

    def test_stores_config(self, config: ClientConfig):
        client = CTraderClient(config)
        assert client._config is config

    def test_creates_transport(self, config: ClientConfig):
        client = CTraderClient(config)
        assert isinstance(client._transport, Transport)
        assert client._transport.host == config.host
        assert client._transport.port == config.port

    def test_creates_protocol(self, config: ClientConfig):
        client = CTraderClient(config)
        assert isinstance(client._protocol, Protocol)

    def test_creates_heartbeat_manager(self, config: ClientConfig):
        client = CTraderClient(config)
        assert isinstance(client._heartbeat, HeartbeatManager)

    def test_creates_event_emitter(self, config: ClientConfig):
        client = CTraderClient(config)
        assert isinstance(client._emitter, EventEmitter)

    def test_creates_event_router(self, config: ClientConfig):
        client = CTraderClient(config)
        assert isinstance(client._router, EventRouter)

    def test_creates_auth_manager(self, config: ClientConfig):
        client = CTraderClient(config)
        assert isinstance(client._auth, AuthManager)

    def test_creates_accounts_api(self, config: ClientConfig):
        client = CTraderClient(config)
        assert isinstance(client._accounts, AccountsAPI)

    def test_creates_symbols_api(self, config: ClientConfig):
        client = CTraderClient(config)
        assert isinstance(client._symbols, SymbolsAPI)

    def test_creates_trading_api(self, config: ClientConfig):
        client = CTraderClient(config)
        assert isinstance(client._trading, TradingAPI)

    def test_creates_market_data_api(self, config: ClientConfig):
        client = CTraderClient(config)
        assert isinstance(client._market_data, MarketDataAPI)

    def test_starts_not_connected(self, config: ClientConfig):
        client = CTraderClient(config)
        assert client._connected is False


class TestCTraderClientProperties:
    """Test CTraderClient property accessors."""

    def test_auth_returns_auth_manager(self, config: ClientConfig):
        client = CTraderClient(config)
        assert client.auth is client._auth

    def test_accounts_returns_accounts_api(self, config: ClientConfig):
        client = CTraderClient(config)
        assert client.accounts is client._accounts

    def test_symbols_returns_symbols_api(self, config: ClientConfig):
        client = CTraderClient(config)
        assert client.symbols is client._symbols

    def test_trading_returns_trading_api(self, config: ClientConfig):
        client = CTraderClient(config)
        assert client.trading is client._trading

    def test_market_data_returns_market_data_api(self, config: ClientConfig):
        client = CTraderClient(config)
        assert client.market_data is client._market_data

    def test_protocol_returns_protocol(self, config: ClientConfig):
        client = CTraderClient(config)
        assert client.protocol is client._protocol

    def test_is_connected_false_when_not_connected(self, config: ClientConfig):
        client = CTraderClient(config)
        assert client.is_connected is False

    def test_is_connected_true_when_connected(self, config: ClientConfig):
        client = CTraderClient(config)
        client._connected = True
        client._transport._stream = MagicMock()  # Simulate connected transport
        assert client.is_connected is True

    def test_is_connected_false_when_transport_disconnected(self, config: ClientConfig):
        client = CTraderClient(config)
        client._connected = True
        # Transport stream is None by default (not connected)
        assert client.is_connected is False


class TestCTraderClientConnect:
    """Test CTraderClient.connect()."""

    @pytest.mark.anyio
    async def test_connect_calls_transport_connect(self, config: ClientConfig):
        client = CTraderClient(config)
        client._transport.connect = AsyncMock()
        client._protocol.start = AsyncMock()
        client._heartbeat.start = AsyncMock()
        client._router.start = MagicMock()

        await client.connect()

        client._transport.connect.assert_called_once()

    @pytest.mark.anyio
    async def test_connect_calls_protocol_start(self, config: ClientConfig):
        client = CTraderClient(config)
        client._transport.connect = AsyncMock()
        client._protocol.start = AsyncMock()
        client._heartbeat.start = AsyncMock()
        client._router.start = MagicMock()

        await client.connect()

        client._protocol.start.assert_called_once()

    @pytest.mark.anyio
    async def test_connect_calls_heartbeat_start(self, config: ClientConfig):
        client = CTraderClient(config)
        client._transport.connect = AsyncMock()
        client._protocol.start = AsyncMock()
        client._heartbeat.start = AsyncMock()
        client._router.start = MagicMock()

        await client.connect()

        client._heartbeat.start.assert_called_once()

    @pytest.mark.anyio
    async def test_connect_calls_router_start(self, config: ClientConfig):
        client = CTraderClient(config)
        client._transport.connect = AsyncMock()
        client._protocol.start = AsyncMock()
        client._heartbeat.start = AsyncMock()
        client._router.start = MagicMock()

        await client.connect()

        client._router.start.assert_called_once()

    @pytest.mark.anyio
    async def test_connect_sets_connected_flag(self, config: ClientConfig):
        client = CTraderClient(config)
        client._transport.connect = AsyncMock()
        client._protocol.start = AsyncMock()
        client._heartbeat.start = AsyncMock()
        client._router.start = MagicMock()

        await client.connect()

        assert client._connected is True

    @pytest.mark.anyio
    async def test_connect_is_idempotent(self, config: ClientConfig):
        client = CTraderClient(config)
        client._transport.connect = AsyncMock()
        client._protocol.start = AsyncMock()
        client._heartbeat.start = AsyncMock()
        client._router.start = MagicMock()

        await client.connect()
        await client.connect()  # Second call should be no-op

        client._transport.connect.assert_called_once()


class TestCTraderClientClose:
    """Test CTraderClient.close()."""

    @pytest.mark.anyio
    async def test_close_calls_router_stop(self, config: ClientConfig):
        client = CTraderClient(config)
        client._connected = True
        client._router.stop = MagicMock()
        client._auth.stop = AsyncMock()
        client._heartbeat.stop = AsyncMock()
        client._protocol.stop = AsyncMock()
        client._transport.close = AsyncMock()

        await client.close()

        client._router.stop.assert_called_once()

    @pytest.mark.anyio
    async def test_close_calls_auth_stop(self, config: ClientConfig):
        client = CTraderClient(config)
        client._connected = True
        client._router.stop = MagicMock()
        client._auth.stop = AsyncMock()
        client._heartbeat.stop = AsyncMock()
        client._protocol.stop = AsyncMock()
        client._transport.close = AsyncMock()

        await client.close()

        client._auth.stop.assert_called_once()

    @pytest.mark.anyio
    async def test_close_calls_heartbeat_stop(self, config: ClientConfig):
        client = CTraderClient(config)
        client._connected = True
        client._router.stop = MagicMock()
        client._auth.stop = AsyncMock()
        client._heartbeat.stop = AsyncMock()
        client._protocol.stop = AsyncMock()
        client._transport.close = AsyncMock()

        await client.close()

        client._heartbeat.stop.assert_called_once()

    @pytest.mark.anyio
    async def test_close_calls_protocol_stop(self, config: ClientConfig):
        client = CTraderClient(config)
        client._connected = True
        client._router.stop = MagicMock()
        client._auth.stop = AsyncMock()
        client._heartbeat.stop = AsyncMock()
        client._protocol.stop = AsyncMock()
        client._transport.close = AsyncMock()

        await client.close()

        client._protocol.stop.assert_called_once()

    @pytest.mark.anyio
    async def test_close_calls_transport_close(self, config: ClientConfig):
        client = CTraderClient(config)
        client._connected = True
        client._router.stop = MagicMock()
        client._auth.stop = AsyncMock()
        client._heartbeat.stop = AsyncMock()
        client._protocol.stop = AsyncMock()
        client._transport.close = AsyncMock()

        await client.close()

        client._transport.close.assert_called_once()

    @pytest.mark.anyio
    async def test_close_sets_connected_flag_false(self, config: ClientConfig):
        client = CTraderClient(config)
        client._connected = True
        client._router.stop = MagicMock()
        client._auth.stop = AsyncMock()
        client._heartbeat.stop = AsyncMock()
        client._protocol.stop = AsyncMock()
        client._transport.close = AsyncMock()

        await client.close()

        assert client._connected is False

    @pytest.mark.anyio
    async def test_close_is_idempotent(self, config: ClientConfig):
        client = CTraderClient(config)
        client._connected = False
        client._router.stop = MagicMock()
        client._auth.stop = AsyncMock()
        client._heartbeat.stop = AsyncMock()
        client._protocol.stop = AsyncMock()
        client._transport.close = AsyncMock()

        await client.close()

        client._router.stop.assert_not_called()
        client._transport.close.assert_not_called()


class TestCTraderClientContextManager:
    """Test CTraderClient async context manager."""

    @pytest.mark.anyio
    async def test_aenter_calls_connect(self, config: ClientConfig):
        client = CTraderClient(config)
        client._transport.connect = AsyncMock()
        client._protocol.start = AsyncMock()
        client._heartbeat.start = AsyncMock()
        client._router.start = MagicMock()
        client._router.stop = MagicMock()
        client._auth.stop = AsyncMock()
        client._heartbeat.stop = AsyncMock()
        client._protocol.stop = AsyncMock()
        client._transport.close = AsyncMock()

        async with client:
            client._transport.connect.assert_called_once()

    @pytest.mark.anyio
    async def test_aenter_returns_client(self, config: ClientConfig):
        client = CTraderClient(config)
        client._transport.connect = AsyncMock()
        client._protocol.start = AsyncMock()
        client._heartbeat.start = AsyncMock()
        client._router.start = MagicMock()
        client._router.stop = MagicMock()
        client._auth.stop = AsyncMock()
        client._heartbeat.stop = AsyncMock()
        client._protocol.stop = AsyncMock()
        client._transport.close = AsyncMock()

        async with client as ctx:
            assert ctx is client

    @pytest.mark.anyio
    async def test_aexit_calls_close(self, config: ClientConfig):
        client = CTraderClient(config)
        client._transport.connect = AsyncMock()
        client._protocol.start = AsyncMock()
        client._heartbeat.start = AsyncMock()
        client._router.start = MagicMock()
        client._router.stop = MagicMock()
        client._auth.stop = AsyncMock()
        client._heartbeat.stop = AsyncMock()
        client._protocol.stop = AsyncMock()
        client._transport.close = AsyncMock()

        async with client:
            pass

        client._transport.close.assert_called_once()

    @pytest.mark.anyio
    async def test_aexit_closes_on_exception(self, config: ClientConfig):
        client = CTraderClient(config)
        client._transport.connect = AsyncMock()
        client._protocol.start = AsyncMock()
        client._heartbeat.start = AsyncMock()
        client._router.start = MagicMock()
        client._router.stop = MagicMock()
        client._auth.stop = AsyncMock()
        client._heartbeat.stop = AsyncMock()
        client._protocol.stop = AsyncMock()
        client._transport.close = AsyncMock()

        with pytest.raises(ValueError):
            async with client:
                raise ValueError("test error")

        client._transport.close.assert_called_once()


class TestCTraderClientEventOn:
    """Test CTraderClient.on() decorator."""

    def test_on_returns_decorator(self, config: ClientConfig):
        client = CTraderClient(config)
        decorator = client.on(SpotEvent)
        assert callable(decorator)

    def test_on_decorator_returns_handler(self, config: ClientConfig):
        client = CTraderClient(config)

        async def my_handler(_event: SpotEvent) -> None:
            pass

        result = client.on(SpotEvent)(my_handler)
        assert result is my_handler

    def test_on_registers_handler_with_emitter(self, config: ClientConfig):
        client = CTraderClient(config)
        client._emitter.subscribe = MagicMock()

        async def my_handler(_event: SpotEvent) -> None:
            pass

        client.on(SpotEvent)(my_handler)

        client._emitter.subscribe.assert_called_once_with(
            SpotEvent,
            my_handler,
            account_id=None,
            symbol_id=None,
        )

    def test_on_passes_account_id_filter(self, config: ClientConfig):
        client = CTraderClient(config)
        client._emitter.subscribe = MagicMock()

        async def my_handler(_event: SpotEvent) -> None:
            pass

        client.on(SpotEvent, account_id=12345)(my_handler)

        client._emitter.subscribe.assert_called_once_with(
            SpotEvent,
            my_handler,
            account_id=12345,
            symbol_id=None,
        )

    def test_on_passes_symbol_id_filter(self, config: ClientConfig):
        client = CTraderClient(config)
        client._emitter.subscribe = MagicMock()

        async def my_handler(_event: SpotEvent) -> None:
            pass

        client.on(SpotEvent, symbol_id=270)(my_handler)

        client._emitter.subscribe.assert_called_once_with(
            SpotEvent,
            my_handler,
            account_id=None,
            symbol_id=270,
        )

    def test_on_passes_both_filters(self, config: ClientConfig):
        client = CTraderClient(config)
        client._emitter.subscribe = MagicMock()

        async def my_handler(_event: SpotEvent) -> None:
            pass

        client.on(SpotEvent, account_id=12345, symbol_id=270)(my_handler)

        client._emitter.subscribe.assert_called_once_with(
            SpotEvent,
            my_handler,
            account_id=12345,
            symbol_id=270,
        )


class TestCTraderClientEventOff:
    """Test CTraderClient.off() method."""

    def test_off_calls_emitter_unsubscribe(self, config: ClientConfig):
        client = CTraderClient(config)
        client._emitter.unsubscribe = MagicMock(return_value=True)

        async def my_handler(_event: SpotEvent) -> None:
            pass

        result = client.off(SpotEvent, my_handler)

        client._emitter.unsubscribe.assert_called_once_with(SpotEvent, my_handler)
        assert result is True

    def test_off_returns_false_when_handler_not_found(self, config: ClientConfig):
        client = CTraderClient(config)
        client._emitter.unsubscribe = MagicMock(return_value=False)

        async def my_handler(_event: SpotEvent) -> None:
            pass

        result = client.off(SpotEvent, my_handler)

        assert result is False
