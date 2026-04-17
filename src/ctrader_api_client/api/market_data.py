from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING

from .._internal.proto import (
    ProtoOAGetTickDataReq,
    ProtoOAGetTickDataRes,
    ProtoOAGetTrendbarsReq,
    ProtoOAGetTrendbarsRes,
    ProtoOAQuoteType,
    ProtoOASubscribeDepthQuotesReq,
    ProtoOASubscribeDepthQuotesRes,
    ProtoOASubscribeLiveTrendbarReq,
    ProtoOASubscribeLiveTrendbarRes,
    ProtoOASubscribeSpotsReq,
    ProtoOASubscribeSpotsRes,
    ProtoOATrendbarPeriod,
    ProtoOAUnsubscribeDepthQuotesReq,
    ProtoOAUnsubscribeDepthQuotesRes,
    ProtoOAUnsubscribeLiveTrendbarReq,
    ProtoOAUnsubscribeLiveTrendbarRes,
    ProtoOAUnsubscribeSpotsReq,
    ProtoOAUnsubscribeSpotsRes,
)
from ..enums import TrendbarPeriod
from ..exceptions import APIError
from ..models import TickData, Trendbar


if TYPE_CHECKING:
    from ..connection import Protocol


# Map TrendbarPeriod enum to proto values
_PERIOD_TO_PROTO: dict[TrendbarPeriod, int] = {
    TrendbarPeriod.M1: ProtoOATrendbarPeriod.M1,
    TrendbarPeriod.M2: ProtoOATrendbarPeriod.M2,
    TrendbarPeriod.M3: ProtoOATrendbarPeriod.M3,
    TrendbarPeriod.M4: ProtoOATrendbarPeriod.M4,
    TrendbarPeriod.M5: ProtoOATrendbarPeriod.M5,
    TrendbarPeriod.M10: ProtoOATrendbarPeriod.M10,
    TrendbarPeriod.M15: ProtoOATrendbarPeriod.M15,
    TrendbarPeriod.M30: ProtoOATrendbarPeriod.M30,
    TrendbarPeriod.H1: ProtoOATrendbarPeriod.H1,
    TrendbarPeriod.H4: ProtoOATrendbarPeriod.H4,
    TrendbarPeriod.H12: ProtoOATrendbarPeriod.H12,
    TrendbarPeriod.D1: ProtoOATrendbarPeriod.D1,
    TrendbarPeriod.W1: ProtoOATrendbarPeriod.W1,
    TrendbarPeriod.MN1: ProtoOATrendbarPeriod.MN1,
}


class MarketDataAPI:
    """Market data subscriptions and historical data.

    Provides methods to subscribe to real-time market data (spots, trendbars,
    depth of market) and retrieve historical data.

    Example:
        ```python
        # Subscribe to spot prices
        await client.market_data.subscribe_spots(account_id, [270, 271])


        # Handle spot events via decorator
        @client.on(SpotEvent, symbol_id=270)
        async def on_eurusd(event: SpotEvent) -> None:
            print(f"EURUSD: {event.bid}/{event.ask}")


        # Get historical candles
        trendbars = await client.market_data.get_trendbars(
            account_id,
            symbol_id=270,
            period=TrendbarPeriod.H1,
            from_timestamp=start,
            to_timestamp=end,
        )
        ```
    """

    def __init__(self, protocol: Protocol, default_timeout: float = 30.0) -> None:
        """Initialize the market data API.

        Args:
            protocol: The protocol instance for sending requests.
            default_timeout: Default request timeout in seconds.
        """
        self._protocol = protocol
        self._default_timeout = default_timeout

    # -------------------------------------------------------------------------
    # Spot Subscriptions
    # -------------------------------------------------------------------------

    async def subscribe_spots(
        self,
        account_id: int,
        symbol_ids: list[int],
        timeout: float | None = None,
    ) -> None:
        """Subscribe to spot price updates.

        After subscribing, spot events will be delivered via the event system.
        Use `@client.on(SpotEvent)` to handle them.

        Args:
            account_id: The cTID trader account ID.
            symbol_ids: Symbols to subscribe to.
            timeout: Request timeout (uses default if None).

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        request = ProtoOASubscribeSpotsReq(
            ctid_trader_account_id=account_id,
            symbol_id=symbol_ids,
            subscribe_to_spot_timestamp=True,
        )

        response = await self._protocol.send_request(
            request,
            timeout=timeout or self._default_timeout,
        )

        if not isinstance(response, ProtoOASubscribeSpotsRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOASubscribeSpotsRes, got {type(response).__name__}",
            )

    async def unsubscribe_spots(
        self,
        account_id: int,
        symbol_ids: list[int],
        timeout: float | None = None,
    ) -> None:
        """Unsubscribe from spot price updates.

        Args:
            account_id: The cTID trader account ID.
            symbol_ids: Symbols to unsubscribe from.
            timeout: Request timeout (uses default if None).

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        request = ProtoOAUnsubscribeSpotsReq(
            ctid_trader_account_id=account_id,
            symbol_id=symbol_ids,
        )

        response = await self._protocol.send_request(
            request,
            timeout=timeout or self._default_timeout,
        )

        if not isinstance(response, ProtoOAUnsubscribeSpotsRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOAUnsubscribeSpotsRes, got {type(response).__name__}",
            )

    # -------------------------------------------------------------------------
    # Trendbar Subscriptions
    # -------------------------------------------------------------------------

    async def subscribe_trendbars(
        self,
        account_id: int,
        symbol_id: int,
        period: TrendbarPeriod,
        timeout: float | None = None,
    ) -> None:
        """Subscribe to live trendbar (candle) updates.

        Requires subscribing to spots for the same symbol beforehand.

        After subscribing, trendbar data will be delivered via the event system inside the SpotEvent object.
        Use `@client.on(SpotEvent)` to handle them.

        Args:
            account_id: The cTID trader account ID.
            symbol_id: Symbol to subscribe to.
            period: Trendbar period (M1, H1, D1, etc.).
            timeout: Request timeout (uses default if None).

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        request = ProtoOASubscribeLiveTrendbarReq(
            ctid_trader_account_id=account_id,
            symbol_id=symbol_id,
            period=ProtoOATrendbarPeriod(_PERIOD_TO_PROTO[period]),
        )

        response = await self._protocol.send_request(
            request,
            timeout=timeout or self._default_timeout,
        )

        if not isinstance(response, ProtoOASubscribeLiveTrendbarRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOASubscribeLiveTrendbarRes, got {type(response).__name__}",
            )

    async def unsubscribe_trendbars(
        self,
        account_id: int,
        symbol_id: int,
        period: TrendbarPeriod,
        timeout: float | None = None,
    ) -> None:
        """Unsubscribe from live trendbar updates.

        Args:
            account_id: The cTID trader account ID.
            symbol_id: Symbol to unsubscribe from.
            period: Trendbar period.
            timeout: Request timeout (uses default if None).

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        request = ProtoOAUnsubscribeLiveTrendbarReq(
            ctid_trader_account_id=account_id,
            symbol_id=symbol_id,
            period=ProtoOATrendbarPeriod(_PERIOD_TO_PROTO[period]),
        )

        response = await self._protocol.send_request(
            request,
            timeout=timeout or self._default_timeout,
        )

        if not isinstance(response, ProtoOAUnsubscribeLiveTrendbarRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOAUnsubscribeLiveTrendbarRes, got {type(response).__name__}",
            )

    # -------------------------------------------------------------------------
    # Depth Subscriptions
    # -------------------------------------------------------------------------

    async def subscribe_depth(
        self,
        account_id: int,
        symbol_ids: list[int],
        timeout: float | None = None,
    ) -> None:
        """Subscribe to depth of market (order book) updates.

        After subscribing, depth events will be delivered via the event system.
        Use `@client.on(DepthEvent)` to handle them.

        Args:
            account_id: The cTID trader account ID.
            symbol_ids: Symbols to subscribe to.
            timeout: Request timeout (uses default if None).

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        request = ProtoOASubscribeDepthQuotesReq(
            ctid_trader_account_id=account_id,
            symbol_id=symbol_ids,
        )

        response = await self._protocol.send_request(
            request,
            timeout=timeout or self._default_timeout,
        )

        if not isinstance(response, ProtoOASubscribeDepthQuotesRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOASubscribeDepthQuotesRes, got {type(response).__name__}",
            )

    async def unsubscribe_depth(
        self,
        account_id: int,
        symbol_ids: list[int],
        timeout: float | None = None,
    ) -> None:
        """Unsubscribe from depth of market updates.

        Args:
            account_id: The cTID trader account ID.
            symbol_ids: Symbols to unsubscribe from.
            timeout: Request timeout (uses default if None).

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        request = ProtoOAUnsubscribeDepthQuotesReq(
            ctid_trader_account_id=account_id,
            symbol_id=symbol_ids,
        )

        response = await self._protocol.send_request(
            request,
            timeout=timeout or self._default_timeout,
        )

        if not isinstance(response, ProtoOAUnsubscribeDepthQuotesRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOAUnsubscribeDepthQuotesRes, got {type(response).__name__}",
            )

    # -------------------------------------------------------------------------
    # Historical Data
    # -------------------------------------------------------------------------

    async def get_trendbars(
        self,
        account_id: int,
        symbol_id: int,
        period: TrendbarPeriod,
        from_timestamp: datetime,
        to_timestamp: datetime,
        timeout: float | None = None,
    ) -> list[Trendbar]:
        """Get historical trendbars (candles).

        Args:
            account_id: The cTID trader account ID.
            symbol_id: Symbol to get data for.
            period: Trendbar period (M1, H1, D1, etc.).
            from_timestamp: Start of time range (inclusive).
            to_timestamp: End of time range (inclusive).
            timeout: Request timeout (uses default if None).

        Returns:
            List of Trendbar objects, ordered by timestamp ascending.

        Note:
            The server may limit the number of bars returned per request.
            For large ranges, consider paginating with smaller time windows.

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        request = ProtoOAGetTrendbarsReq(
            ctid_trader_account_id=account_id,
            symbol_id=symbol_id,
            period=ProtoOATrendbarPeriod(_PERIOD_TO_PROTO[period]),
            from_timestamp=int(from_timestamp.timestamp() * 1000),
            to_timestamp=int(to_timestamp.timestamp() * 1000),
        )

        response = await self._protocol.send_request(
            request,
            timeout=timeout or self._default_timeout,
        )

        if not isinstance(response, ProtoOAGetTrendbarsRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOAGetTrendbarsRes, got {type(response).__name__}",
            )

        return [Trendbar.from_proto(t) for t in response.trendbar]

    async def get_tick_data(
        self,
        account_id: int,
        symbol_id: int,
        from_timestamp: datetime,
        to_timestamp: datetime,
        quote_type: str = "BID",
        timeout: float | None = None,
    ) -> Sequence[TickData]:
        """Get historical tick data.

        Args:
            account_id: The cTID trader account ID.
            symbol_id: Symbol to get data for.
            from_timestamp: Start of time range (inclusive).
            to_timestamp: End of time range (inclusive).
            quote_type: "BID" or "ASK".
            timeout: Request timeout (uses default if None).

        Returns:
            List of TickData objects, ordered by newest first.

        Note:
            Tick data can be voluminous. Use small time windows to avoid
            timeout issues and excessive memory usage.

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        qt = ProtoOAQuoteType.BID if quote_type.upper() == "BID" else ProtoOAQuoteType.ASK

        request = ProtoOAGetTickDataReq(
            ctid_trader_account_id=account_id,
            symbol_id=symbol_id,
            type=qt,
            from_timestamp=int(from_timestamp.timestamp() * 1000),
            to_timestamp=int(to_timestamp.timestamp() * 1000),
        )

        response = await self._protocol.send_request(
            request,
            timeout=timeout or self._default_timeout,
        )

        if not isinstance(response, ProtoOAGetTickDataRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOAGetTickDataRes, got {type(response).__name__}",
            )

        return TickData.from_proto_list(response.tick_data)
