from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from .._internal.proto import ProtoOAAccessRights, ProtoOAAccountType
from ..enums import AccessRights, AccountType
from ._base import FrozenModel


if TYPE_CHECKING:
    from .._internal.proto import ProtoOACtidTraderAccount, ProtoOATrader


def _timestamp_to_datetime(timestamp_ms: int) -> datetime:
    """Convert millisecond timestamp to datetime."""
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)


_ACCOUNT_TYPE_MAP: dict[int, AccountType] = {
    ProtoOAAccountType.HEDGED: AccountType.HEDGED,
    ProtoOAAccountType.NETTED: AccountType.NETTED,
    ProtoOAAccountType.SPREAD_BETTING: AccountType.SPREAD_BETTING,
}

_ACCESS_RIGHTS_MAP: dict[int, AccessRights] = {
    ProtoOAAccessRights.FULL_ACCESS: AccessRights.FULL_ACCESS,
    ProtoOAAccessRights.CLOSE_ONLY: AccessRights.CLOSE_ONLY,
    ProtoOAAccessRights.NO_TRADING: AccessRights.NO_TRADING,
    ProtoOAAccessRights.NO_LOGIN: AccessRights.NO_LOGIN,
}


class AccountSummary(FrozenModel):
    """Summary of a trading account from account list.

    This is the lightweight representation returned when listing accounts
    associated with an access token. Use Account for full details after
    authorization.

    Attributes:
        account_id: The cTID trader account ID.
        is_live: True if this is a live account, False for demo.
        trader_login: The trader's login number.
        broker_name: Short name of the broker.
        last_closing_deal_timestamp: Timestamp of last closing deal, or None.
        last_balance_update_timestamp: Timestamp of last balance update, or None.
    """

    account_id: int
    is_live: bool
    trader_login: int
    broker_name: str
    last_closing_deal_timestamp: datetime | None = None
    last_balance_update_timestamp: datetime | None = None

    @classmethod
    def from_proto(cls, proto: ProtoOACtidTraderAccount) -> AccountSummary:
        """Create AccountSummary from proto message.

        Args:
            proto: The proto message to convert.

        Returns:
            A new AccountSummary instance.
        """
        return cls(
            account_id=proto.ctid_trader_account_id,
            is_live=proto.is_live,
            trader_login=proto.trader_login,
            broker_name=proto.broker_title_short or "",
            last_closing_deal_timestamp=(
                _timestamp_to_datetime(proto.last_closing_deal_timestamp) if proto.last_closing_deal_timestamp else None
            ),
            last_balance_update_timestamp=(
                _timestamp_to_datetime(proto.last_balance_update_timestamp)
                if proto.last_balance_update_timestamp
                else None
            ),
        )


class Account(FrozenModel):
    """Full trading account details.

    Retrieved after authorizing a specific account. Contains balance,
    leverage, and other trading parameters.

    Attributes:
        account_id: The cTID trader account ID.
        trader_login: The trader's login number.
        balance: Account balance (raw integer, use get_balance() for Decimal).
        money_digits: Decimal places for monetary values.
        leverage_in_cents: Account leverage in cents (e.g., 10000 = 1:100).
        account_type: Account type (HEDGED, NETTED, SPREAD_BETTING).
        access_rights: Current access rights for the account.
        broker_name: Name of the broker.
        deposit_asset_id: Asset ID of the deposit currency.
        swap_free: Whether account is swap-free (Islamic Banking).
        is_limited_risk: Whether account has limited risk mode.
        registration_timestamp: When the account was registered.
        max_leverage: Maximum allowed leverage.
        balance_version: Version number for balance updates.
        manager_bonus: Manager bonus amount (raw integer).
        ib_bonus: IB bonus amount (raw integer).
        non_withdrawable_bonus: Non-withdrawable bonus amount (raw integer).
    """

    account_id: int
    trader_login: int
    balance: int
    money_digits: int
    leverage_in_cents: int
    account_type: AccountType
    access_rights: AccessRights
    broker_name: str
    deposit_asset_id: int
    swap_free: bool
    is_limited_risk: bool
    registration_timestamp: datetime | None = None

    # Optional fields
    max_leverage: int | None = None
    balance_version: int | None = None
    manager_bonus: int | None = None
    ib_bonus: int | None = None
    non_withdrawable_bonus: int | None = None

    def get_balance(self) -> Decimal:
        """Get balance as Decimal.

        Returns:
            Balance divided by 10^money_digits.
        """
        return Decimal(self.balance) / Decimal(10**self.money_digits)

    def get_leverage(self) -> str:
        """Get leverage as human-readable string.

        Returns:
            Leverage string like "1:100".
        """
        leverage = self.leverage_in_cents // 100
        return f"1:{leverage}"

    @classmethod
    def from_proto(cls, proto: ProtoOATrader) -> Account:
        """Create Account from proto message.

        Args:
            proto: The proto message to convert.

        Returns:
            A new Account instance.
        """
        return cls(
            account_id=proto.ctid_trader_account_id,
            trader_login=proto.trader_login,
            balance=proto.balance,
            money_digits=proto.money_digits if proto.money_digits else 2,
            leverage_in_cents=proto.leverage_in_cents,
            account_type=_ACCOUNT_TYPE_MAP.get(proto.account_type, AccountType.HEDGED),
            access_rights=_ACCESS_RIGHTS_MAP.get(proto.access_rights, AccessRights.FULL_ACCESS),
            broker_name=proto.broker_name or "",
            deposit_asset_id=proto.deposit_asset_id,
            swap_free=proto.swap_free,
            is_limited_risk=proto.is_limited_risk,
            registration_timestamp=(
                _timestamp_to_datetime(proto.registration_timestamp) if proto.registration_timestamp else None
            ),
            max_leverage=proto.max_leverage if proto.max_leverage else None,
            balance_version=proto.balance_version if proto.balance_version else None,
            manager_bonus=proto.manager_bonus if proto.manager_bonus else None,
            ib_bonus=proto.ib_bonus if proto.ib_bonus else None,
            non_withdrawable_bonus=proto.non_withdrawable_bonus if proto.non_withdrawable_bonus else None,
        )
