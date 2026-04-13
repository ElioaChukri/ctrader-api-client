from __future__ import annotations

from typing import TYPE_CHECKING

from .._internal.proto import (
    ProtoOATraderReq,
    ProtoOATraderRes,
)
from ..exceptions import APIError
from ..models import Account


if TYPE_CHECKING:
    from ..connection import Protocol


class AccountsAPI:
    """Account information operations.

    Provides methods to retrieve account/trader details.

    Example:
        ```python
        account = await client.accounts.get_trader(account_id)
        print(f"Balance: {account.get_balance()}")
        print(f"Leverage: {account.get_leverage()}")
        ```
    """

    def __init__(self, protocol: Protocol, default_timeout: float = 30.0) -> None:
        """Initialize the accounts API.

        Args:
            protocol: The protocol instance for sending requests.
            default_timeout: Default request timeout in seconds.
        """
        self._protocol = protocol
        self._default_timeout = default_timeout

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

        response = await self._protocol.send_request(
            request,
            timeout=timeout or self._default_timeout,
        )

        if not isinstance(response, ProtoOATraderRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOATraderRes, got {type(response).__name__}",
            )

        return Account.from_proto(response.trader)
