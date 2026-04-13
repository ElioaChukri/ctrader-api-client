from __future__ import annotations

from typing import TYPE_CHECKING

from .._internal.proto import (
    ProtoOASymbolByIdReq,
    ProtoOASymbolByIdRes,
    ProtoOASymbolsListReq,
    ProtoOASymbolsListRes,
)
from ..exceptions import APIError
from ..models import Symbol, SymbolInfo


if TYPE_CHECKING:
    from ..connection import Protocol


class SymbolsAPI:
    """Symbol information and search operations.

    Provides methods to list, retrieve, and search trading symbols.

    Example:
        ```python
        # List all available symbols
        symbols = await client.symbols.list_all(account_id)

        # Search for EUR pairs
        eur_pairs = await client.symbols.search(account_id, "EUR")

        # Get full details for specific symbols
        eurusd = await client.symbols.get_by_id(account_id, 270)
        ```
    """

    def __init__(self, protocol: Protocol, default_timeout: float = 30.0) -> None:
        """Initialize the symbols API.

        Args:
            protocol: The protocol instance for sending requests.
            default_timeout: Default request timeout in seconds.
        """
        self._protocol = protocol
        self._default_timeout = default_timeout

    async def list_all(
        self,
        account_id: int,
        timeout: float | None = None,
    ) -> list[SymbolInfo]:
        """List all available symbols (lightweight info).

        Returns basic symbol information without full trading parameters.
        Use `get_by_ids()` for complete symbol details.

        Args:
            account_id: The cTID trader account ID.
            timeout: Request timeout (uses default if None).

        Returns:
            List of SymbolInfo objects with basic symbol data.

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        request = ProtoOASymbolsListReq(ctid_trader_account_id=account_id)

        response = await self._protocol.send_request(
            request,
            timeout=timeout or self._default_timeout,
        )

        if not isinstance(response, ProtoOASymbolsListRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOASymbolsListRes, got {type(response).__name__}",
            )

        return [SymbolInfo.from_proto(s) for s in response.symbol]

    async def get_by_ids(
        self,
        account_id: int,
        symbol_ids: list[int],
        timeout: float | None = None,
    ) -> list[Symbol]:
        """Get full symbol details by IDs.

        Args:
            account_id: The cTID trader account ID.
            symbol_ids: List of symbol IDs to retrieve.
            timeout: Request timeout (uses default if None).

        Returns:
            List of Symbol objects with full trading parameters.

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        request = ProtoOASymbolByIdReq(
            ctid_trader_account_id=account_id,
            symbol_id=symbol_ids,
        )

        response = await self._protocol.send_request(
            request,
            timeout=timeout or self._default_timeout,
        )

        if not isinstance(response, ProtoOASymbolByIdRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOASymbolByIdRes, got {type(response).__name__}",
            )

        return [Symbol.from_proto(s) for s in response.symbol]

    async def get_by_id(
        self,
        account_id: int,
        symbol_id: int,
        timeout: float | None = None,
    ) -> Symbol:
        """Get a single symbol by ID.

        Args:
            account_id: The cTID trader account ID.
            symbol_id: The symbol ID.
            timeout: Request timeout (uses default if None).

        Returns:
            Symbol with full trading parameters.

        Raises:
            ValueError: If symbol not found.
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        symbols = await self.get_by_ids(account_id, [symbol_id], timeout)
        if not symbols:
            raise ValueError(f"Symbol {symbol_id} not found")
        return symbols[0]

    async def search(
        self,
        account_id: int,
        query: str,
        timeout: float | None = None,
    ) -> list[SymbolInfo]:
        """Search symbols by name.

        Performs case-insensitive substring matching on symbol names.

        Args:
            account_id: The cTID trader account ID.
            query: Search string (e.g., "EUR", "BTCUSD").
            timeout: Request timeout (uses default if None).

        Returns:
            List of matching SymbolInfo objects.

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        all_symbols = await self.list_all(account_id, timeout)
        query_upper = query.upper()
        return [s for s in all_symbols if query_upper in s.name.upper()]
