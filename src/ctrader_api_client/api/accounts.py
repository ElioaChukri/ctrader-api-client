from __future__ import annotations

from .._internal.proto import (
    ProtoOATraderReq,
    ProtoOATraderRes,
)
from ..models import Account
from ._base import BaseAPI


class AccountsAPI(BaseAPI):
    """Account information operations.

    Provides methods to retrieve account/trader details.

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
