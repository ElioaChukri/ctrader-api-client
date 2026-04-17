"""Tests for AccountsAPI."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ctrader_api_client._internal.proto import (
    ProtoOAAccessRights,
    ProtoOAAccountType,
    ProtoOATrader,
    ProtoOATraderReq,
    ProtoOATraderRes,
)
from ctrader_api_client.api import AccountsAPI
from ctrader_api_client.enums import AccessRights, AccountType
from ctrader_api_client.exceptions import APIError


class TestAccountsAPIInit:
    """Test AccountsAPI initialization."""

    def test_stores_protocol(self, mock_protocol: MagicMock):
        api = AccountsAPI(mock_protocol)
        assert api._protocol is mock_protocol

    def test_default_timeout(self, mock_protocol: MagicMock):
        api = AccountsAPI(mock_protocol)
        assert api._default_timeout == 30.0

    def test_custom_timeout(self, mock_protocol: MagicMock):
        api = AccountsAPI(mock_protocol, default_timeout=60.0)
        assert api._default_timeout == 60.0


class TestGetTrader:
    """Test AccountsAPI.get_trader()."""

    @pytest.fixture
    def trader_response(self) -> ProtoOATraderRes:
        """Create a sample trader response."""
        return ProtoOATraderRes(
            trader=ProtoOATrader(
                ctid_trader_account_id=12345,
                trader_login=67890,
                balance=100000,
                money_digits=2,
                leverage_in_cents=10000,
                account_type=ProtoOAAccountType.HEDGED,
                access_rights=ProtoOAAccessRights.FULL_ACCESS,
                broker_name="Test Broker",
                deposit_asset_id=1,
                swap_free=False,
                is_limited_risk=False,
            )
        )

    @pytest.mark.anyio
    async def test_sends_correct_request(
        self,
        mock_protocol: MagicMock,
        trader_response: ProtoOATraderRes,
    ):
        mock_protocol.send_request.return_value = trader_response
        api = AccountsAPI(mock_protocol)

        await api.get_trader(12345)

        mock_protocol.send_request.assert_called_once()
        request = mock_protocol.send_request.call_args[0][0]
        assert isinstance(request, ProtoOATraderReq)
        assert request.ctid_trader_account_id == 12345

    @pytest.mark.anyio
    async def test_returns_account_model(
        self,
        mock_protocol: MagicMock,
        trader_response: ProtoOATraderRes,
    ):
        mock_protocol.send_request.return_value = trader_response
        api = AccountsAPI(mock_protocol)

        account = await api.get_trader(12345)

        assert account.account_id == 12345
        assert account.trader_login == 67890
        assert account.balance == 1000.0  # 100000 / 10^2
        assert account.leverage_in_cents == 10000
        assert account.account_type == AccountType.HEDGED
        assert account.access_rights == AccessRights.FULL_ACCESS
        assert account.broker_name == "Test Broker"

    @pytest.mark.anyio
    async def test_uses_custom_timeout(
        self,
        mock_protocol: MagicMock,
        trader_response: ProtoOATraderRes,
    ):
        mock_protocol.send_request.return_value = trader_response
        api = AccountsAPI(mock_protocol)

        await api.get_trader(12345, timeout=45.0)

        mock_protocol.send_request.assert_called_once()
        assert mock_protocol.send_request.call_args[1]["timeout"] == 45.0

    @pytest.mark.anyio
    async def test_raises_on_unexpected_response(self, mock_protocol: MagicMock):
        mock_protocol.send_request.return_value = MagicMock()
        api = AccountsAPI(mock_protocol)

        with pytest.raises(APIError) as exc_info:
            await api.get_trader(12345)

        assert exc_info.value.error_code == "UNEXPECTED_RESPONSE"
