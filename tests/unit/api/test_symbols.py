"""Tests for SymbolsAPI."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ctrader_api_client._internal.proto import (
    ProtoOALightSymbol,
    ProtoOASymbol,
    ProtoOASymbolByIdReq,
    ProtoOASymbolByIdRes,
    ProtoOASymbolsListReq,
    ProtoOASymbolsListRes,
    ProtoOATradingMode,
)
from ctrader_api_client.api import SymbolsAPI
from ctrader_api_client.enums import TradingMode
from ctrader_api_client.exceptions import APIError


class TestSymbolsAPIInit:
    """Test SymbolsAPI initialization."""

    def test_stores_protocol(self, mock_protocol: MagicMock):
        api = SymbolsAPI(mock_protocol)
        assert api._protocol is mock_protocol

    def test_default_timeout(self, mock_protocol: MagicMock):
        api = SymbolsAPI(mock_protocol)
        assert api._default_timeout == 30.0


class TestListAll:
    """Test SymbolsAPI.list_all()."""

    @pytest.fixture
    def symbols_list_response(self) -> ProtoOASymbolsListRes:
        """Create a sample symbols list response."""
        return ProtoOASymbolsListRes(
            symbol=[
                ProtoOALightSymbol(
                    symbol_id=270,
                    symbol_name="EURUSD",
                    enabled=True,
                    base_asset_id=1,
                    quote_asset_id=2,
                ),
                ProtoOALightSymbol(
                    symbol_id=271,
                    symbol_name="GBPUSD",
                    enabled=True,
                    base_asset_id=3,
                    quote_asset_id=2,
                ),
            ]
        )

    @pytest.mark.anyio
    async def test_sends_correct_request(
        self,
        mock_protocol: MagicMock,
        symbols_list_response: ProtoOASymbolsListRes,
    ):
        mock_protocol.send_request.return_value = symbols_list_response
        api = SymbolsAPI(mock_protocol)

        await api.list_all(12345)

        mock_protocol.send_request.assert_called_once()
        request = mock_protocol.send_request.call_args[0][0]
        assert isinstance(request, ProtoOASymbolsListReq)
        assert request.ctid_trader_account_id == 12345

    @pytest.mark.anyio
    async def test_returns_symbol_info_list(
        self,
        mock_protocol: MagicMock,
        symbols_list_response: ProtoOASymbolsListRes,
    ):
        mock_protocol.send_request.return_value = symbols_list_response
        api = SymbolsAPI(mock_protocol)

        symbols = await api.list_all(12345)

        assert len(symbols) == 2
        assert symbols[0].symbol_id == 270
        assert symbols[0].name == "EURUSD"
        assert symbols[1].symbol_id == 271
        assert symbols[1].name == "GBPUSD"

    @pytest.mark.anyio
    async def test_raises_on_unexpected_response(self, mock_protocol: MagicMock):
        mock_protocol.send_request.return_value = MagicMock()
        api = SymbolsAPI(mock_protocol)

        with pytest.raises(APIError) as exc_info:
            await api.list_all(12345)

        assert exc_info.value.error_code == "UNEXPECTED_RESPONSE"


class TestGetByIds:
    """Test SymbolsAPI.get_by_ids()."""

    @pytest.fixture
    def symbol_by_id_response(self) -> ProtoOASymbolByIdRes:
        """Create a sample symbol by ID response."""
        return ProtoOASymbolByIdRes(
            symbol=[
                ProtoOASymbol(
                    symbol_id=270,
                    digits=5,
                    pip_position=4,
                    lot_size=100000,
                    min_volume=100,
                    max_volume=10000000,
                    step_volume=100,
                    trading_mode=ProtoOATradingMode.ENABLED,
                    swap_long=-0.5,
                    swap_short=0.3,
                ),
            ]
        )

    @pytest.mark.anyio
    async def test_sends_correct_request(
        self,
        mock_protocol: MagicMock,
        symbol_by_id_response: ProtoOASymbolByIdRes,
    ):
        mock_protocol.send_request.return_value = symbol_by_id_response
        api = SymbolsAPI(mock_protocol)

        await api.get_by_ids(12345, [270, 271])

        mock_protocol.send_request.assert_called_once()
        request = mock_protocol.send_request.call_args[0][0]
        assert isinstance(request, ProtoOASymbolByIdReq)
        assert request.ctid_trader_account_id == 12345
        assert list(request.symbol_id) == [270, 271]

    @pytest.mark.anyio
    async def test_returns_symbol_list(
        self,
        mock_protocol: MagicMock,
        symbol_by_id_response: ProtoOASymbolByIdRes,
    ):
        mock_protocol.send_request.return_value = symbol_by_id_response
        api = SymbolsAPI(mock_protocol)

        symbols = await api.get_by_ids(12345, [270])

        assert len(symbols) == 1
        assert symbols[0].symbol_id == 270
        assert symbols[0].digits == 5
        assert symbols[0].pip_position == 4
        assert symbols[0].lot_size == 100000
        assert symbols[0].trading_mode == TradingMode.ENABLED


class TestGetById:
    """Test SymbolsAPI.get_by_id()."""

    @pytest.fixture
    def symbol_by_id_response(self) -> ProtoOASymbolByIdRes:
        """Create a sample symbol by ID response."""
        return ProtoOASymbolByIdRes(
            symbol=[
                ProtoOASymbol(
                    symbol_id=270,
                    digits=5,
                    pip_position=4,
                    lot_size=100000,
                    min_volume=100,
                    max_volume=10000000,
                    step_volume=100,
                    trading_mode=ProtoOATradingMode.ENABLED,
                    swap_long=-0.5,
                    swap_short=0.3,
                ),
            ]
        )

    @pytest.mark.anyio
    async def test_returns_single_symbol(
        self,
        mock_protocol: MagicMock,
        symbol_by_id_response: ProtoOASymbolByIdRes,
    ):
        mock_protocol.send_request.return_value = symbol_by_id_response
        api = SymbolsAPI(mock_protocol)

        symbol = await api.get_by_id(12345, 270)

        assert symbol.symbol_id == 270

    @pytest.mark.anyio
    async def test_raises_when_not_found(self, mock_protocol: MagicMock):
        mock_protocol.send_request.return_value = ProtoOASymbolByIdRes(symbol=[])
        api = SymbolsAPI(mock_protocol)

        with pytest.raises(ValueError) as exc_info:
            await api.get_by_id(12345, 999)

        assert "999" in str(exc_info.value)


class TestSearch:
    """Test SymbolsAPI.search()."""

    @pytest.fixture
    def symbols_list_response(self) -> ProtoOASymbolsListRes:
        """Create a sample symbols list response."""
        return ProtoOASymbolsListRes(
            symbol=[
                ProtoOALightSymbol(
                    symbol_id=270,
                    symbol_name="EURUSD",
                    enabled=True,
                    base_asset_id=1,
                    quote_asset_id=2,
                ),
                ProtoOALightSymbol(
                    symbol_id=271,
                    symbol_name="GBPUSD",
                    enabled=True,
                    base_asset_id=3,
                    quote_asset_id=2,
                ),
                ProtoOALightSymbol(
                    symbol_id=272,
                    symbol_name="EURGBP",
                    enabled=True,
                    base_asset_id=1,
                    quote_asset_id=3,
                ),
            ]
        )

    @pytest.mark.anyio
    async def test_filters_by_name(
        self,
        mock_protocol: MagicMock,
        symbols_list_response: ProtoOASymbolsListRes,
    ):
        mock_protocol.send_request.return_value = symbols_list_response
        api = SymbolsAPI(mock_protocol)

        symbols = await api.search(12345, "EUR")

        assert len(symbols) == 2
        assert symbols[0].name == "EURUSD"
        assert symbols[1].name == "EURGBP"

    @pytest.mark.anyio
    async def test_case_insensitive(
        self,
        mock_protocol: MagicMock,
        symbols_list_response: ProtoOASymbolsListRes,
    ):
        mock_protocol.send_request.return_value = symbols_list_response
        api = SymbolsAPI(mock_protocol)

        symbols = await api.search(12345, "eur")

        assert len(symbols) == 2

    @pytest.mark.anyio
    async def test_no_matches_returns_empty(
        self,
        mock_protocol: MagicMock,
        symbols_list_response: ProtoOASymbolsListRes,
    ):
        mock_protocol.send_request.return_value = symbols_list_response
        api = SymbolsAPI(mock_protocol)

        symbols = await api.search(12345, "XYZ")

        assert len(symbols) == 0
