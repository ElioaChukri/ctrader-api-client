from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
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
from ..events import EventPublisher, SubscriptionRestoreFailedEvent
from ..models import TickData, Trendbar
from ._base import BaseAPI


if TYPE_CHECKING:
    from ..connection import Protocol


logger = logging.getLogger(__name__)


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


@dataclass
class _StandingSubscriptions:
    """What one account has asked for, kept so it can be re-applied later."""

    spots: set[int] = field(default_factory=set)
    trendbars: set[tuple[int, TrendbarPeriod]] = field(default_factory=set)
    depth: set[int] = field(default_factory=set)


class MarketDataAPI(BaseAPI):
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

    def __init__(
        self,
        protocol: Protocol,
        publisher: EventPublisher,
        default_timeout: float = 30.0,
    ) -> None:
        """Initialize the market data namespace.

        Args:
            protocol: The protocol instance for sending requests.
            publisher: Where SubscriptionRestoreFailedEvent is published.
            default_timeout: Default request timeout in seconds.
        """
        super().__init__(protocol, default_timeout)
        self._publisher = publisher
        self._standing: dict[int, _StandingSubscriptions] = {}

    def _standing_for(self, account_id: int) -> _StandingSubscriptions:
        """The record of what this account has asked for, created on first use."""
        return self._standing.setdefault(account_id, _StandingSubscriptions())

    def forget(self, account_id: int) -> None:
        """Drop what this account had asked for, so nothing is restored for it.

        Called when the account leaves the auth manager. Without this the
        record outlives the session it describes, and an account authenticated
        again later would silently have subscriptions it never asked for
        re-applied.

        Args:
            account_id: The account whose standing subscriptions to discard.
        """
        self._standing.pop(account_id, None)

    async def restore(self, account_id: int) -> None:
        """Re-apply this account's standing subscriptions to a fresh session.

        A server-side session carries its own subscriptions, so anything the
        account had asked for is gone once that session ends. Called after
        re-authentication, before the account is announced as ready, so a
        consumer's handler does not race a half-restored feed.

        Restoration stops at the first failure and reports it, keeping the
        intent so the next reconnection tries again.

        Args:
            account_id: The account whose subscriptions to re-apply.
        """
        standing = self._standing.get(account_id)
        if standing is None:
            return

        try:
            if standing.spots:
                await self.subscribe_spots(account_id, sorted(standing.spots))

            # Trendbars are rejected unless spots for the symbol are live.
            for symbol_id, period in sorted(standing.trendbars, key=lambda item: (item[0], item[1].name)):
                await self.subscribe_trendbars(account_id, symbol_id, period)

            if standing.depth:
                await self.subscribe_depth(account_id, sorted(standing.depth))
        except Exception as e:
            logger.error("Failed to restore subscriptions for account %d: %s", account_id, e)
            await self._publisher.emit(SubscriptionRestoreFailedEvent(account_id=account_id, error=e))

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
        logger.debug("Subscribing to spots: account=%d symbols=%s", account_id, symbol_ids)
        request = ProtoOASubscribeSpotsReq(
            ctid_trader_account_id=account_id,
            symbol_id=symbol_ids,
            subscribe_to_spot_timestamp=True,
        )

        await self._protocol.request(
            request,
            ProtoOASubscribeSpotsRes,
            timeout=self._timeout(timeout),
        )
        self._standing_for(account_id).spots.update(symbol_ids)

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
        logger.debug("Unsubscribing from spots: account=%d symbols=%s", account_id, symbol_ids)
        request = ProtoOAUnsubscribeSpotsReq(
            ctid_trader_account_id=account_id,
            symbol_id=symbol_ids,
        )

        await self._protocol.request(
            request,
            ProtoOAUnsubscribeSpotsRes,
            timeout=self._timeout(timeout),
        )
        self._standing_for(account_id).spots.difference_update(symbol_ids)

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
        logger.debug("Subscribing to trendbars: account=%d symbol=%d period=%s", account_id, symbol_id, period.name)
        request = ProtoOASubscribeLiveTrendbarReq(
            ctid_trader_account_id=account_id,
            symbol_id=symbol_id,
            period=ProtoOATrendbarPeriod(_PERIOD_TO_PROTO[period]),
        )

        await self._protocol.request(
            request,
            ProtoOASubscribeLiveTrendbarRes,
            timeout=self._timeout(timeout),
        )
        self._standing_for(account_id).trendbars.add((symbol_id, period))

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
        logger.debug("Unsubscribing from trendbars: account=%d symbol=%d period=%s", account_id, symbol_id, period.name)
        request = ProtoOAUnsubscribeLiveTrendbarReq(
            ctid_trader_account_id=account_id,
            symbol_id=symbol_id,
            period=ProtoOATrendbarPeriod(_PERIOD_TO_PROTO[period]),
        )

        await self._protocol.request(
            request,
            ProtoOAUnsubscribeLiveTrendbarRes,
            timeout=self._timeout(timeout),
        )
        self._standing_for(account_id).trendbars.discard((symbol_id, period))

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
        logger.debug("Subscribing to depth: account=%d symbols=%s", account_id, symbol_ids)
        request = ProtoOASubscribeDepthQuotesReq(
            ctid_trader_account_id=account_id,
            symbol_id=symbol_ids,
        )

        await self._protocol.request(
            request,
            ProtoOASubscribeDepthQuotesRes,
            timeout=self._timeout(timeout),
        )
        self._standing_for(account_id).depth.update(symbol_ids)

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
        logger.debug("Unsubscribing from depth: account=%d symbols=%s", account_id, symbol_ids)
        request = ProtoOAUnsubscribeDepthQuotesReq(
            ctid_trader_account_id=account_id,
            symbol_id=symbol_ids,
        )

        await self._protocol.request(
            request,
            ProtoOAUnsubscribeDepthQuotesRes,
            timeout=self._timeout(timeout),
        )
        self._standing_for(account_id).depth.difference_update(symbol_ids)

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

        response = await self._protocol.request(
            request,
            ProtoOAGetTrendbarsRes,
            timeout=self._timeout(timeout),
        )

        return [Trendbar.from_proto(t, historical=True) for t in response.trendbar]

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

        response = await self._protocol.request(
            request,
            ProtoOAGetTickDataRes,
            timeout=self._timeout(timeout),
        )

        return TickData.from_proto_list(response.tick_data)
