"""Tests for account models."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from ctrader_api_client.enums import AccessRights, AccountType
from ctrader_api_client.models import Account, AccountSummary


class TestAccountSummary:
    """Tests for AccountSummary model."""

    def test_from_proto_maps_all_fields(self) -> None:
        """Test that from_proto correctly maps all proto fields."""
        proto = MagicMock()
        proto.ctid_trader_account_id = 12345
        proto.is_live = True
        proto.trader_login = 67890
        proto.broker_title_short = "TestBroker"
        proto.last_closing_deal_timestamp = 1704067200000  # 2024-01-01 00:00:00 UTC
        proto.last_balance_update_timestamp = 1704153600000  # 2024-01-02 00:00:00 UTC

        summary = AccountSummary.from_proto(proto)

        assert summary.account_id == 12345
        assert summary.is_live is True
        assert summary.trader_login == 67890
        assert summary.broker_name == "TestBroker"
        assert summary.last_closing_deal_timestamp == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        assert summary.last_balance_update_timestamp == datetime(2024, 1, 2, 0, 0, 0, tzinfo=UTC)

    def test_from_proto_handles_missing_timestamps(self) -> None:
        """Test that from_proto handles None timestamps."""
        proto = MagicMock()
        proto.ctid_trader_account_id = 12345
        proto.is_live = False
        proto.trader_login = 67890
        proto.broker_title_short = ""
        proto.last_closing_deal_timestamp = 0
        proto.last_balance_update_timestamp = 0

        summary = AccountSummary.from_proto(proto)

        assert summary.last_closing_deal_timestamp is None
        assert summary.last_balance_update_timestamp is None
        assert summary.broker_name == ""

    def test_from_proto_handles_none_broker_name(self) -> None:
        """Test that from_proto handles None broker name."""
        proto = MagicMock()
        proto.ctid_trader_account_id = 12345
        proto.is_live = True
        proto.trader_login = 67890
        proto.broker_title_short = None
        proto.last_closing_deal_timestamp = 0
        proto.last_balance_update_timestamp = 0

        summary = AccountSummary.from_proto(proto)

        assert summary.broker_name == ""


class TestAccount:
    """Tests for Account model."""

    def test_from_proto_maps_all_fields(self) -> None:
        """Test that from_proto correctly maps all proto fields."""
        proto = MagicMock()
        proto.ctid_trader_account_id = 12345
        proto.trader_login = 67890
        proto.balance = 1000000  # 10000.00 with 2 digits
        proto.money_digits = 2
        proto.leverage_in_cents = 10000  # 1:100
        proto.account_type = 0  # HEDGED
        proto.access_rights = 0  # FULL_ACCESS
        proto.broker_name = "Test Broker"
        proto.deposit_asset_id = 1
        proto.swap_free = False
        proto.is_limited_risk = False
        proto.registration_timestamp = 1704067200000
        proto.max_leverage = 500
        proto.balance_version = 42
        proto.manager_bonus = 1000  # 10.00
        proto.ib_bonus = 500  # 5.00
        proto.non_withdrawable_bonus = 250  # 2.50

        account = Account.from_proto(proto)

        assert account.account_id == 12345
        assert account.trader_login == 67890
        assert account.balance == 10000.0  # Divided by 10^2
        assert account.leverage_in_cents == 10000
        assert account.account_type == AccountType.HEDGED
        assert account.access_rights == AccessRights.FULL_ACCESS
        assert account.broker_name == "Test Broker"
        assert account.deposit_asset_id == 1
        assert account.swap_free is False
        assert account.is_limited_risk is False
        assert account.registration_timestamp == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        assert account.max_leverage == 500
        assert account.balance_version == 42
        assert account.manager_bonus == 10.0
        assert account.ib_bonus == 5.0
        assert account.non_withdrawable_bonus == 2.50

    def test_from_proto_maps_account_types(self) -> None:
        """Test that all account types are correctly mapped."""
        base_proto = MagicMock()
        base_proto.ctid_trader_account_id = 1
        base_proto.trader_login = 1
        base_proto.balance = 0
        base_proto.money_digits = 2
        base_proto.leverage_in_cents = 100
        base_proto.access_rights = 0
        base_proto.broker_name = ""
        base_proto.deposit_asset_id = 1
        base_proto.swap_free = False
        base_proto.is_limited_risk = False
        base_proto.registration_timestamp = 0
        base_proto.max_leverage = 0
        base_proto.balance_version = 0
        base_proto.manager_bonus = 0
        base_proto.ib_bonus = 0
        base_proto.non_withdrawable_bonus = 0

        test_cases = [
            (0, AccountType.HEDGED),
            (1, AccountType.NETTED),
            (2, AccountType.SPREAD_BETTING),
        ]

        for proto_value, expected_type in test_cases:
            base_proto.account_type = proto_value
            account = Account.from_proto(base_proto)
            assert account.account_type == expected_type

    def test_from_proto_maps_access_rights(self) -> None:
        """Test that all access rights are correctly mapped."""
        base_proto = MagicMock()
        base_proto.ctid_trader_account_id = 1
        base_proto.trader_login = 1
        base_proto.balance = 0
        base_proto.money_digits = 2
        base_proto.leverage_in_cents = 100
        base_proto.account_type = 0
        base_proto.broker_name = ""
        base_proto.deposit_asset_id = 1
        base_proto.swap_free = False
        base_proto.is_limited_risk = False
        base_proto.registration_timestamp = 0
        base_proto.max_leverage = 0
        base_proto.balance_version = 0
        base_proto.manager_bonus = 0
        base_proto.ib_bonus = 0
        base_proto.non_withdrawable_bonus = 0

        test_cases = [
            (0, AccessRights.FULL_ACCESS),
            (1, AccessRights.CLOSE_ONLY),
            (2, AccessRights.NO_TRADING),
            (3, AccessRights.NO_LOGIN),
        ]

        for proto_value, expected_rights in test_cases:
            base_proto.access_rights = proto_value
            account = Account.from_proto(base_proto)
            assert account.access_rights == expected_rights

    def test_balance_is_float(self) -> None:
        """Test balance is directly accessible as float."""
        account = Account(
            account_id=1,
            trader_login=1,
            balance=12345.67,
            leverage_in_cents=10000,
            account_type=AccountType.HEDGED,
            access_rights=AccessRights.FULL_ACCESS,
            broker_name="Test",
            deposit_asset_id=1,
            swap_free=False,
            is_limited_risk=False,
        )

        assert account.balance == 12345.67

    def test_get_leverage_100(self) -> None:
        """Test get_leverage returns 1:100 for 10000 cents."""
        account = Account(
            account_id=1,
            trader_login=1,
            balance=0.0,
            leverage_in_cents=10000,
            account_type=AccountType.HEDGED,
            access_rights=AccessRights.FULL_ACCESS,
            broker_name="Test",
            deposit_asset_id=1,
            swap_free=False,
            is_limited_risk=False,
        )

        assert account.get_leverage() == "1:100"
