from __future__ import annotations

import logging

from .._internal.proto import (
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAGetAccountListByAccessTokenRes,
    ProtoOATraderReq,
    ProtoOATraderRes,
)
from ..exceptions import AccountNotFoundError, APIError, TokenExpiredError
from ..models import Account, AccountSummary
from ._base import BaseAPI


logger = logging.getLogger(__name__)


class AccountsAPI(BaseAPI):
    """Account information operations.

    Provides methods to discover the accounts an access token covers and to
    retrieve account/trader details.

    Example:
        ```python
        account = await client.accounts.get_trader(account_id)
        print(f"Balance: {account.get_balance()}")
        print(f"Leverage: {account.get_leverage()}")
        ```
    """

    async def get_trader(
        self,
        account_id: int,
        timeout: float | None = None,
    ) -> Account:
        """Get full account/trader information.

        Args:
            account_id: The cTID trader account ID.
            timeout: Request timeout (uses default if None).

        Returns:
            Full Account details including balance, leverage, etc.

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        request = ProtoOATraderReq(ctid_trader_account_id=account_id)

        response = await self._protocol.request(
            request,
            ProtoOATraderRes,
            timeout=self._timeout(timeout),
        )

        return Account.from_proto(response.trader)

    async def list_by_token(
        self,
        access_token: str,
        timeout: float | None = None,
    ) -> list[AccountSummary]:
        """List the trading accounts an access token covers.

        Lists them without authenticating any of them, so a caller can discover
        what is available, or let a user pick.

        Args:
            access_token: OAuth access token.
            timeout: Request timeout (uses default if None).

        Returns:
            List of account summaries (lightweight account info).

        Raises:
            TokenExpiredError: If the server rejects the access token.
            APIError: If the request fails for any other reason.
            CTraderConnectionTimeoutError: If request times out.
        """
        request = ProtoOAGetAccountListByAccessTokenReq(access_token=access_token)

        try:
            response = await self._protocol.request(
                request,
                ProtoOAGetAccountListByAccessTokenRes,
                timeout=self._timeout(timeout),
            )
        except APIError as e:
            if e.is_token_failure():
                raise TokenExpiredError from e
            raise

        accounts = [AccountSummary.from_proto(acc) for acc in response.ctid_trader_account]
        logger.debug("Found %d accounts", len(accounts))
        return accounts

    async def resolve_account_id(
        self,
        access_token: str,
        trader_login: int,
        timeout: float | None = None,
    ) -> int:
        """Resolve a trader login to its cTID trader account ID.

        Args:
            access_token: OAuth access token.
            trader_login: The trader login number (visible in cTrader app).
            timeout: Request timeout (uses default if None).

        Returns:
            The cTID trader account ID (used for API calls).

        Raises:
            AccountNotFoundError: If no account matches the trader login.
            TokenExpiredError: If the server rejects the access token.
            APIError: If the request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        accounts = await self.list_by_token(access_token, timeout=timeout)

        for account in accounts:
            if account.trader_login == trader_login:
                logger.debug(
                    "Resolved trader login %d to account ID %d",
                    trader_login,
                    account.account_id,
                )
                return account.account_id

        available_logins = [acc.trader_login for acc in accounts]
        raise AccountNotFoundError(trader_login, available_logins)
