"""Tests for MarketDataAPI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from ctrader_api_client._internal.proto import (
    ProtoOAGetTrendbarsReq,
    ProtoOAGetTrendbarsRes,
    ProtoOASubscribeDepthQuotesReq,
    ProtoOASubscribeDepthQuotesRes,
    ProtoOASubscribeLiveTrendbarReq,
    ProtoOASubscribeLiveTrendbarRes,
    ProtoOASubscribeSpotsReq,
    ProtoOASubscribeSpotsRes,
    ProtoOATrendbar,
    ProtoOATrendbarPeriod,
    ProtoOAUnsubscribeSpotsReq,
    ProtoOAUnsubscribeSpotsRes,
)
from ctrader_api_client.api import MarketDataAPI
from ctrader_api_client.enums import TrendbarPeriod
from ctrader_api_client.exceptions import APIError


class TestMarketDataAPIInit:
    """Test MarketDataAPI initialization."""

    def test_stores_protocol(self, mock_protocol: MagicMock):
        api = MarketDataAPI(mock_protocol)
        assert api._protocol is mock_protocol

    def test_default_timeout(self, mock_protocol: MagicMock):
        api = MarketDataAPI(mock_protocol)
        assert api._default_timeout == 30.0


class TestSubscribeSpots:
    """Test MarketDataAPI.subscribe_spots()."""

    @pytest.mark.anyio
    async def test_sends_correct_request(self, mock_protocol: MagicMock):
        mock_protocol.send_request.return_value = ProtoOASubscribeSpotsRes()
        api = MarketDataAPI(mock_protocol)

        await api.subscribe_spots(12345, [270, 271])

        mock_protocol.send_request.assert_called_once()
        request = mock_protocol.send_request.call_args[0][0]
        assert isinstance(request, ProtoOASubscribeSpotsReq)
        assert request.ctid_trader_account_id == 12345
        assert list(request.symbol_id) == [270, 271]
        assert request.subscribe_to_spot_timestamp is True

    @pytest.mark.anyio
    async def test_raises_on_unexpected_response(self, mock_protocol: MagicMock):
        mock_protocol.send_request.return_value = MagicMock()
        api = MarketDataAPI(mock_protocol)

        with pytest.raises(APIError) as exc_info:
            await api.subscribe_spots(12345, [270])

        assert exc_info.value.error_code == "UNEXPECTED_RESPONSE"


class TestUnsubscribeSpots:
    """Test MarketDataAPI.unsubscribe_spots()."""

    @pytest.mark.anyio
    async def test_sends_correct_request(self, mock_protocol: MagicMock):
        mock_protocol.send_request.return_value = ProtoOAUnsubscribeSpotsRes()
        api = MarketDataAPI(mock_protocol)

        await api.unsubscribe_spots(12345, [270, 271])

        mock_protocol.send_request.assert_called_once()
        request = mock_protocol.send_request.call_args[0][0]
        assert isinstance(request, ProtoOAUnsubscribeSpotsReq)
        assert request.ctid_trader_account_id == 12345
        assert list(request.symbol_id) == [270, 271]


class TestSubscribeTrendbars:
    """Test MarketDataAPI.subscribe_trendbars()."""

    @pytest.mark.anyio
    async def test_sends_correct_request(self, mock_protocol: MagicMock):
        mock_protocol.send_request.return_value = ProtoOASubscribeLiveTrendbarRes()
        api = MarketDataAPI(mock_protocol)

        await api.subscribe_trendbars(12345, 270, TrendbarPeriod.H1)

        mock_protocol.send_request.assert_called_once()
        request = mock_protocol.send_request.call_args[0][0]
        assert isinstance(request, ProtoOASubscribeLiveTrendbarReq)
        assert request.ctid_trader_account_id == 12345
        assert request.symbol_id == 270
        assert request.period == ProtoOATrendbarPeriod.H1

    @pytest.mark.anyio
    async def test_maps_all_periods(self, mock_protocol: MagicMock):
        """Test that all TrendbarPeriod values are mapped correctly."""
        mock_protocol.send_request.return_value = ProtoOASubscribeLiveTrendbarRes()
        api = MarketDataAPI(mock_protocol)

        periods = [
            (TrendbarPeriod.M1, ProtoOATrendbarPeriod.M1),
            (TrendbarPeriod.M5, ProtoOATrendbarPeriod.M5),
            (TrendbarPeriod.M15, ProtoOATrendbarPeriod.M15),
            (TrendbarPeriod.H1, ProtoOATrendbarPeriod.H1),
            (TrendbarPeriod.H4, ProtoOATrendbarPeriod.H4),
            (TrendbarPeriod.D1, ProtoOATrendbarPeriod.D1),
        ]

        for our_period, proto_period in periods:
            mock_protocol.send_request.reset_mock()
            await api.subscribe_trendbars(12345, 270, our_period)
            request = mock_protocol.send_request.call_args[0][0]
            assert request.period == proto_period


class TestSubscribeDepth:
    """Test MarketDataAPI.subscribe_depth()."""

    @pytest.mark.anyio
    async def test_sends_correct_request(self, mock_protocol: MagicMock):
        mock_protocol.send_request.return_value = ProtoOASubscribeDepthQuotesRes()
        api = MarketDataAPI(mock_protocol)

        await api.subscribe_depth(12345, [270])

        mock_protocol.send_request.assert_called_once()
        request = mock_protocol.send_request.call_args[0][0]
        assert isinstance(request, ProtoOASubscribeDepthQuotesReq)
        assert request.ctid_trader_account_id == 12345
        assert list(request.symbol_id) == [270]


class TestGetTrendbars:
    """Test MarketDataAPI.get_trendbars()."""

    @pytest.fixture
    def trendbars_response(self) -> ProtoOAGetTrendbarsRes:
        """Create a sample trendbars response."""
        base_ts_minutes = int(datetime.now(UTC).timestamp() // 60)
        return ProtoOAGetTrendbarsRes(
            trendbar=[
                ProtoOATrendbar(
                    utc_timestamp_in_minutes=base_ts_minutes,
                    low=112000,
                    delta_high=500,
                    delta_open=200,
                    delta_close=400,
                    volume=1000,
                ),
                ProtoOATrendbar(
                    utc_timestamp_in_minutes=base_ts_minutes + 60,  # +1 hour
                    low=112500,
                    delta_high=300,
                    delta_open=100,
                    delta_close=250,
                    volume=800,
                ),
            ],
            period=ProtoOATrendbarPeriod.H1,
        )

    @pytest.mark.anyio
    async def test_sends_correct_request(
        self,
        mock_protocol: MagicMock,
        trendbars_response: ProtoOAGetTrendbarsRes,
    ):
        mock_protocol.send_request.return_value = trendbars_response
        api = MarketDataAPI(mock_protocol)

        from_ts = datetime.now(UTC) - timedelta(hours=2)
        to_ts = datetime.now(UTC)
        await api.get_trendbars(12345, 270, TrendbarPeriod.H1, from_ts, to_ts)

        mock_protocol.send_request.assert_called_once()
        request = mock_protocol.send_request.call_args[0][0]
        assert isinstance(request, ProtoOAGetTrendbarsReq)
        assert request.ctid_trader_account_id == 12345
        assert request.symbol_id == 270
        assert request.period == ProtoOATrendbarPeriod.H1

    @pytest.mark.anyio
    async def test_returns_trendbars(
        self,
        mock_protocol: MagicMock,
        trendbars_response: ProtoOAGetTrendbarsRes,
    ):
        mock_protocol.send_request.return_value = trendbars_response
        api = MarketDataAPI(mock_protocol)

        from_ts = datetime.now(UTC) - timedelta(hours=2)
        to_ts = datetime.now(UTC)
        bars = await api.get_trendbars(12345, 270, TrendbarPeriod.H1, from_ts, to_ts)

        assert len(bars) == 2
        assert bars[0].low == 1.12  # 112000 / 1e5
        assert bars[0].volume == 1000

    @pytest.mark.anyio
    async def test_raises_on_unexpected_response(self, mock_protocol: MagicMock):
        mock_protocol.send_request.return_value = MagicMock()
        api = MarketDataAPI(mock_protocol)

        from_ts = datetime.now(UTC) - timedelta(hours=2)
        to_ts = datetime.now(UTC)

        with pytest.raises(APIError) as exc_info:
            await api.get_trendbars(12345, 270, TrendbarPeriod.H1, from_ts, to_ts)

        assert exc_info.value.error_code == "UNEXPECTED_RESPONSE"
