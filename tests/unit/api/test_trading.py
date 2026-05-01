"""Tests for TradingAPI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from ctrader_api_client._internal.proto import (
    ProtoOACancelOrderReq,
    ProtoOADeal,
    ProtoOADealListReq,
    ProtoOADealListRes,
    ProtoOADealStatus,
    ProtoOAExecutionEvent,
    ProtoOAExecutionType,
    ProtoOAGetPositionUnrealizedPnLReq,
    ProtoOAGetPositionUnrealizedPnLRes,
    ProtoOAOrder,
    ProtoOAOrderListReq,
    ProtoOAOrderListRes,
    ProtoOAOrderStatus,
    ProtoOAOrderType,
    ProtoOAPosition,
    ProtoOAPositionStatus,
    ProtoOAPositionUnrealizedPnL,
    ProtoOAReconcileReq,
    ProtoOAReconcileRes,
    ProtoOATimeInForce,
    ProtoOATradeData,
    ProtoOATradeSide,
)
from ctrader_api_client.api import TradingAPI
from ctrader_api_client.enums import ExecutionType, OrderSide, OrderType
from ctrader_api_client.exceptions import APIError
from ctrader_api_client.models import NewOrderRequest, PositionUnrealizedPnL


class TestGetUnrealizedPnlPerPosition:
    """Test TradingAPI.get_unrealized_pnl_per_position()."""

    @pytest.fixture
    def pnl_response(self) -> ProtoOAGetPositionUnrealizedPnLRes:
        return ProtoOAGetPositionUnrealizedPnLRes(
            ctid_trader_account_id=12345,
            money_digits=2,
            position_unrealized_pn_l=[
                ProtoOAPositionUnrealizedPnL(
                    position_id=200,
                    gross_unrealized_pn_l=1500,
                    net_unrealized_pn_l=1200,
                ),
                ProtoOAPositionUnrealizedPnL(
                    position_id=201,
                    gross_unrealized_pn_l=-500,
                    net_unrealized_pn_l=-600,
                ),
            ],
        )

    @pytest.mark.anyio
    async def test_sends_correct_request(
        self,
        mock_protocol: MagicMock,
        pnl_response: ProtoOAGetPositionUnrealizedPnLRes,
    ):
        mock_protocol.send_request.return_value = pnl_response
        api = TradingAPI(mock_protocol)

        await api.get_unrealized_pnl_per_position(12345)

        mock_protocol.send_request.assert_called_once()
        request = mock_protocol.send_request.call_args[0][0]
        assert isinstance(request, ProtoOAGetPositionUnrealizedPnLReq)
        assert request.ctid_trader_account_id == 12345

    @pytest.mark.anyio
    async def test_applies_money_digits_divisor(
        self,
        mock_protocol: MagicMock,
        pnl_response: ProtoOAGetPositionUnrealizedPnLRes,
    ):
        mock_protocol.send_request.return_value = pnl_response
        api = TradingAPI(mock_protocol)

        result = await api.get_unrealized_pnl_per_position(12345)

        assert len(result) == 2
        assert result[0].position_id == 200
        assert result[0].gross_unrealized_pnl == 15.0
        assert result[0].net_unrealized_pnl == 12.0
        assert result[1].position_id == 201
        assert result[1].gross_unrealized_pnl == -5.0
        assert result[1].net_unrealized_pnl == -6.0

    @pytest.mark.anyio
    async def test_returns_list_of_position_unrealized_pnl(
        self,
        mock_protocol: MagicMock,
        pnl_response: ProtoOAGetPositionUnrealizedPnLRes,
    ):
        mock_protocol.send_request.return_value = pnl_response
        api = TradingAPI(mock_protocol)

        result = await api.get_unrealized_pnl_per_position(12345)

        assert all(isinstance(item, PositionUnrealizedPnL) for item in result)

    @pytest.mark.anyio
    async def test_raises_on_unexpected_response(self, mock_protocol: MagicMock):
        mock_protocol.send_request.return_value = MagicMock()
        api = TradingAPI(mock_protocol)

        with pytest.raises(APIError) as exc_info:
            await api.get_unrealized_pnl_per_position(12345)

        assert exc_info.value.error_code == "UNEXPECTED_RESPONSE"


class TestTradingAPIInit:
    """Test TradingAPI initialization."""

    def test_stores_protocol(self, mock_protocol: MagicMock):
        api = TradingAPI(mock_protocol)
        assert api._protocol is mock_protocol

    def test_default_timeout(self, mock_protocol: MagicMock):
        api = TradingAPI(mock_protocol)
        assert api._default_timeout == 30.0


class TestPlaceOrder:
    """Test TradingAPI.place_order()."""

    @pytest.fixture
    def execution_response(self) -> ProtoOAExecutionEvent:
        """Create a sample execution response."""
        return ProtoOAExecutionEvent(
            ctid_trader_account_id=12345,
            execution_type=ProtoOAExecutionType.ORDER_FILLED,
            order=ProtoOAOrder(
                order_id=100,
                trade_data=ProtoOATradeData(
                    symbol_id=270,
                    volume=1000,
                    trade_side=ProtoOATradeSide.BUY,  # BUY
                ),
                order_type=ProtoOAOrderType.MARKET,
                order_status=ProtoOAOrderStatus.ORDER_STATUS_FILLED,
                time_in_force=ProtoOATimeInForce.GOOD_TILL_CANCEL,
            ),
            position=ProtoOAPosition(
                position_id=200,
                position_status=ProtoOAPositionStatus.POSITION_STATUS_OPEN,
            ),
            deal=ProtoOADeal(
                deal_id=300,
                order_id=100,
                position_id=200,
                symbol_id=270,
                volume=1000,
                filled_volume=1000,
                execution_price=1.12345,
                execution_timestamp=int(datetime.now(UTC).timestamp() * 1000),
                trade_side=ProtoOATradeSide.BUY,
                deal_status=ProtoOADealStatus.FILLED,
            ),
        )

    @pytest.mark.anyio
    async def test_returns_execution_event(
        self,
        mock_protocol: MagicMock,
        execution_response: ProtoOAExecutionEvent,
    ):
        mock_protocol.send_request.return_value = execution_response
        api = TradingAPI(mock_protocol)

        request = NewOrderRequest(
            symbol_id=270,
            side=OrderSide.BUY,
            volume=1000,
            order_type=OrderType.MARKET,
        )
        result = await api.place_order(12345, request)

        assert result.execution_type == ExecutionType.ORDER_FILLED
        assert result.order_id == 100
        assert result.position_id == 200
        assert result.symbol_id == 270
        assert result.side == OrderSide.BUY
        assert result.filled_volume == 1000

    @pytest.mark.anyio
    async def test_raises_on_unexpected_response(self, mock_protocol: MagicMock):
        mock_protocol.send_request.return_value = MagicMock()
        api = TradingAPI(mock_protocol)

        request = NewOrderRequest(
            symbol_id=270,
            side=OrderSide.BUY,
            volume=1000,
            order_type=OrderType.MARKET,
        )

        with pytest.raises(APIError) as exc_info:
            await api.place_order(12345, request)

        assert exc_info.value.error_code == "UNEXPECTED_RESPONSE"


class TestCancelOrder:
    """Test TradingAPI.cancel_order()."""

    @pytest.fixture
    def cancel_response(self) -> ProtoOAExecutionEvent:
        """Create a sample cancel response."""
        return ProtoOAExecutionEvent(
            ctid_trader_account_id=12345,
            execution_type=ProtoOAExecutionType.ORDER_CANCELLED,
            order=ProtoOAOrder(
                order_id=100,
                trade_data=ProtoOATradeData(
                    symbol_id=270,
                    volume=1000,
                    trade_side=ProtoOATradeSide.BUY,
                ),
                order_type=ProtoOAOrderType.LIMIT,
                order_status=ProtoOAOrderStatus.ORDER_STATUS_CANCELLED,
                time_in_force=ProtoOATimeInForce.GOOD_TILL_CANCEL,
            ),
        )

    @pytest.mark.anyio
    async def test_sends_correct_request(
        self,
        mock_protocol: MagicMock,
        cancel_response: ProtoOAExecutionEvent,
    ):
        mock_protocol.send_request.return_value = cancel_response
        api = TradingAPI(mock_protocol)

        await api.cancel_order(12345, 100)

        mock_protocol.send_request.assert_called_once()
        request = mock_protocol.send_request.call_args[0][0]
        assert isinstance(request, ProtoOACancelOrderReq)
        assert request.ctid_trader_account_id == 12345
        assert request.order_id == 100

    @pytest.mark.anyio
    async def test_returns_execution_event(
        self,
        mock_protocol: MagicMock,
        cancel_response: ProtoOAExecutionEvent,
    ):
        mock_protocol.send_request.return_value = cancel_response
        api = TradingAPI(mock_protocol)

        result = await api.cancel_order(12345, 100)

        assert result.execution_type == ExecutionType.ORDER_CANCELLED
        assert result.order_id == 100


class TestGetOpenPositions:
    """Test TradingAPI.get_open_positions()."""

    @pytest.fixture
    def reconcile_response(self) -> ProtoOAReconcileRes:
        """Create a sample reconcile response."""
        return ProtoOAReconcileRes(
            position=[
                ProtoOAPosition(
                    position_id=200,
                    trade_data=ProtoOATradeData(
                        symbol_id=270,
                        volume=1000,
                        trade_side=ProtoOATradeSide.BUY,
                        open_timestamp=int(datetime.now(UTC).timestamp() * 1000),
                    ),
                    position_status=ProtoOAPositionStatus.POSITION_STATUS_OPEN,
                    price=1.12345,
                ),
            ]
        )

    @pytest.mark.anyio
    async def test_sends_correct_request(
        self,
        mock_protocol: MagicMock,
        reconcile_response: ProtoOAReconcileRes,
    ):
        mock_protocol.send_request.return_value = reconcile_response
        api = TradingAPI(mock_protocol)

        await api.get_open_positions(12345)

        mock_protocol.send_request.assert_called_once()
        request = mock_protocol.send_request.call_args[0][0]
        assert isinstance(request, ProtoOAReconcileReq)
        assert request.ctid_trader_account_id == 12345

    @pytest.mark.anyio
    async def test_returns_positions(
        self,
        mock_protocol: MagicMock,
        reconcile_response: ProtoOAReconcileRes,
    ):
        mock_protocol.send_request.return_value = reconcile_response
        api = TradingAPI(mock_protocol)

        positions = await api.get_open_positions(12345)

        assert len(positions) == 1
        assert positions[0].position_id == 200
        assert positions[0].symbol_id == 270


class TestGetPendingOrders:
    """Test TradingAPI.get_pending_orders()."""

    @pytest.fixture
    def order_list_response(self) -> ProtoOAOrderListRes:
        """Create a sample order list response."""
        return ProtoOAOrderListRes(
            order=[
                ProtoOAOrder(
                    order_id=100,
                    trade_data=ProtoOATradeData(
                        symbol_id=270,
                        volume=1000,
                        trade_side=ProtoOATradeSide.BUY,
                        open_timestamp=int(datetime.now(UTC).timestamp() * 1000),
                    ),
                    order_type=ProtoOAOrderType.LIMIT,
                    order_status=ProtoOAOrderStatus.ORDER_STATUS_ACCEPTED,
                    time_in_force=ProtoOATimeInForce.GOOD_TILL_CANCEL,
                    limit_price=1.12000,
                ),
            ]
        )

    @pytest.mark.anyio
    async def test_sends_correct_request(
        self,
        mock_protocol: MagicMock,
        order_list_response: ProtoOAOrderListRes,
    ):
        mock_protocol.send_request.return_value = order_list_response
        api = TradingAPI(mock_protocol)

        await api.get_pending_orders(12345)

        mock_protocol.send_request.assert_called_once()
        request = mock_protocol.send_request.call_args[0][0]
        assert isinstance(request, ProtoOAOrderListReq)
        assert request.ctid_trader_account_id == 12345

    @pytest.mark.anyio
    async def test_returns_orders(
        self,
        mock_protocol: MagicMock,
        order_list_response: ProtoOAOrderListRes,
    ):
        mock_protocol.send_request.return_value = order_list_response
        api = TradingAPI(mock_protocol)

        orders = await api.get_pending_orders(12345)

        assert len(orders) == 1
        assert orders[0].order_id == 100
        assert orders[0].symbol_id == 270
        assert orders[0].order_type == OrderType.LIMIT


class TestGetDeals:
    """Test TradingAPI.get_deals()."""

    @pytest.fixture
    def deal_list_response(self) -> ProtoOADealListRes:
        """Create a sample deal list response."""
        return ProtoOADealListRes(
            deal=[
                ProtoOADeal(
                    deal_id=300,
                    order_id=100,
                    position_id=200,
                    symbol_id=270,
                    volume=1000,
                    filled_volume=1000,
                    execution_price=1.12345,
                    execution_timestamp=int(datetime.now(UTC).timestamp() * 1000),
                    trade_side=ProtoOATradeSide.BUY,
                    deal_status=ProtoOADealStatus.FILLED,
                ),
            ]
        )

    @pytest.mark.anyio
    async def test_sends_correct_request(
        self,
        mock_protocol: MagicMock,
        deal_list_response: ProtoOADealListRes,
    ):
        mock_protocol.send_request.return_value = deal_list_response
        api = TradingAPI(mock_protocol)

        from_ts = datetime.now(UTC) - timedelta(days=1)
        to_ts = datetime.now(UTC)
        await api.get_deals(12345, from_ts, to_ts)

        mock_protocol.send_request.assert_called_once()
        request = mock_protocol.send_request.call_args[0][0]
        assert isinstance(request, ProtoOADealListReq)
        assert request.ctid_trader_account_id == 12345

    @pytest.mark.anyio
    async def test_returns_deals(
        self,
        mock_protocol: MagicMock,
        deal_list_response: ProtoOADealListRes,
    ):
        mock_protocol.send_request.return_value = deal_list_response
        api = TradingAPI(mock_protocol)

        from_ts = datetime.now(UTC) - timedelta(days=1)
        to_ts = datetime.now(UTC)
        deals = await api.get_deals(12345, from_ts, to_ts)

        assert len(deals) == 1
        assert deals[0].deal_id == 300
        assert deals[0].symbol_id == 270
