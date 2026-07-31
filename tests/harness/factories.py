"""Builders for proto messages and credentials used across the suite.

Every builder returns a realistic, fully-formed message with sensible defaults
so tests only state the fields they actually care about.
"""

from __future__ import annotations

import time

from ctrader_api_client._internal.proto import (
    ProtoOAAccountAuthRes,
    ProtoOAApplicationAuthRes,
    ProtoOACtidTraderAccount,
    ProtoOAErrorRes,
    ProtoOAGetAccountListByAccessTokenRes,
    ProtoOARefreshTokenRes,
    ProtoOASpotEvent,
    ProtoOATrendbar,
)
from ctrader_api_client.auth import AccountCredentials


ACCOUNT_ID = 12345678
OTHER_ACCOUNT_ID = 87654321
TRADER_LOGIN = 17091452
SYMBOL_ID = 270
ACCESS_TOKEN = "access-token"  # noqa: S105 - test fixture value, not a secret
REFRESH_TOKEN = "refresh-token"  # noqa: S105 - test fixture value, not a secret

# Prices cross the wire as integers scaled by this factor.
PRICE_SCALE = 100_000


def credentials(
    account_id: int = ACCOUNT_ID,
    access_token: str = ACCESS_TOKEN,
    refresh_token: str = REFRESH_TOKEN,
    expires_in: float = 3600.0,
) -> AccountCredentials:
    """Credentials expiring `expires_in` seconds from now."""
    return AccountCredentials(
        account_id=account_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=time.time() + expires_in,
    )


def app_auth_res() -> ProtoOAApplicationAuthRes:
    """A successful application authentication response."""
    return ProtoOAApplicationAuthRes()


def account_auth_res(account_id: int = ACCOUNT_ID) -> ProtoOAAccountAuthRes:
    """A successful account authentication response."""
    return ProtoOAAccountAuthRes(ctid_trader_account_id=account_id)


def ctid_account(
    account_id: int = ACCOUNT_ID,
    trader_login: int = TRADER_LOGIN,
    is_live: bool = True,
    broker_title_short: str = "TestBroker",
    last_closing_deal_timestamp: int = 0,
    last_balance_update_timestamp: int = 0,
) -> ProtoOACtidTraderAccount:
    """A single account entry as returned by the account list endpoint."""
    return ProtoOACtidTraderAccount(
        ctid_trader_account_id=account_id,
        is_live=is_live,
        trader_login=trader_login,
        broker_title_short=broker_title_short,
        last_closing_deal_timestamp=last_closing_deal_timestamp,
        last_balance_update_timestamp=last_balance_update_timestamp,
    )


def account_list_res(*accounts: ProtoOACtidTraderAccount) -> ProtoOAGetAccountListByAccessTokenRes:
    """An account list response containing the given accounts."""
    return ProtoOAGetAccountListByAccessTokenRes(ctid_trader_account=list(accounts) or [ctid_account()])


def refresh_token_res(
    access_token: str = "new-access-token",  # noqa: S107 - test fixture value
    refresh_token: str = "new-refresh-token",  # noqa: S107 - test fixture value
    expires_in: int = 7200,
) -> ProtoOARefreshTokenRes:
    """A successful token refresh response."""
    return ProtoOARefreshTokenRes(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


def error_res(
    error_code: str = "SOMETHING_WENT_WRONG",
    description: str = "",
    account_id: int = 0,
    maintenance_end_timestamp: int = 0,
    retry_after: int = 0,
) -> ProtoOAErrorRes:
    """An error response."""
    return ProtoOAErrorRes(
        error_code=error_code,
        description=description,
        ctid_trader_account_id=account_id,
        maintenance_end_timestamp=maintenance_end_timestamp,
        retry_after=retry_after,
    )


def spot_event(
    account_id: int = ACCOUNT_ID,
    symbol_id: int = SYMBOL_ID,
    bid: int = 108_500,
    ask: int = 108_700,
    timestamp: int = 1_700_000_000_000,
    trendbar: list[ProtoOATrendbar] | None = None,
) -> ProtoOASpotEvent:
    """A spot price event with integer-scaled prices."""
    return ProtoOASpotEvent(
        ctid_trader_account_id=account_id,
        symbol_id=symbol_id,
        bid=bid,
        ask=ask,
        timestamp=timestamp,
        trendbar=trendbar if trendbar is not None else [],
    )
