from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from .._internal.proto import (
    ProtoOACancelOrderReq,
    ProtoOADealListByPositionIdReq,
    ProtoOADealListByPositionIdRes,
    ProtoOADealListReq,
    ProtoOADealListRes,
    ProtoOAExecutionEvent,
    ProtoOAExecutionType,
    ProtoOAOrderErrorEvent,
    ProtoOAOrderListReq,
    ProtoOAOrderListRes,
    ProtoOAReconcileReq,
    ProtoOAReconcileRes,
    ProtoOAv1PnLChangeSubscribeReq,
    ProtoOAv1PnLChangeSubscribeRes,
)
from ..enums import ExecutionType, OrderSide
from ..events import ExecutionEvent
from ..exceptions import APIError
from ..models import Deal, Order, Position
from ..models.requests import (
    AmendOrderRequest,
    AmendPositionRequest,
    ClosePositionRequest,
    NewOrderRequest,
)


if TYPE_CHECKING:
    from ..connection import Protocol


logger = logging.getLogger(__name__)


def _raise_if_order_error(response: object) -> None:
    """Raise APIError if response is an order error event.

    Args:
        response: The response to check.

    Raises:
        APIError: If response is a ProtoOAOrderErrorEvent.
    """
    if isinstance(response, ProtoOAOrderErrorEvent):
        raise APIError(
            error_code=response.error_code or "ORDER_ERROR",
            description=response.description or None,
            ctid_trader_account_id=response.ctid_trader_account_id or None,
        )


# Map ProtoOAExecutionType enum values to our ExecutionType
_EXECUTION_TYPE_MAP: dict[int, ExecutionType] = {
    ProtoOAExecutionType.ORDER_ACCEPTED: ExecutionType.ORDER_ACCEPTED,
    ProtoOAExecutionType.ORDER_FILLED: ExecutionType.ORDER_FILLED,
    ProtoOAExecutionType.ORDER_REPLACED: ExecutionType.ORDER_REPLACED,
    ProtoOAExecutionType.ORDER_CANCELLED: ExecutionType.ORDER_CANCELLED,
    ProtoOAExecutionType.ORDER_EXPIRED: ExecutionType.ORDER_EXPIRED,
    ProtoOAExecutionType.ORDER_REJECTED: ExecutionType.ORDER_REJECTED,
    ProtoOAExecutionType.ORDER_CANCEL_REJECTED: ExecutionType.ORDER_CANCEL_REJECTED,
    ProtoOAExecutionType.SWAP: ExecutionType.SWAP,
    ProtoOAExecutionType.DEPOSIT_WITHDRAW: ExecutionType.DEPOSIT_WITHDRAW,
    ProtoOAExecutionType.ORDER_PARTIAL_FILL: ExecutionType.ORDER_PARTIAL_FILL,
    ProtoOAExecutionType.BONUS_DEPOSIT_WITHDRAW: ExecutionType.BONUS_DEPOSIT_WITHDRAW,
}


def _proto_to_execution_event(proto: ProtoOAExecutionEvent) -> ExecutionEvent:
    """Convert ProtoOAExecutionEvent to ExecutionEvent.

    Args:
        proto: The proto message to convert.

    Returns:
        ExecutionEvent instance.

    Raises:
        APIError: If execution type is unknown.
    """
    exec_type = _EXECUTION_TYPE_MAP.get(proto.execution_type)
    if exec_type is None:
        raise APIError(
            error_code="UNKNOWN_EXECUTION_TYPE",
            description=f"Unknown execution type: {proto.execution_type}",
        )

    # Map order side
    side = OrderSide.BUY
    if proto.order and proto.order.trade_data:
        if proto.order.trade_data.trade_side == 2:
            side = OrderSide.SELL

    # Extract order details
    order_id = proto.order.order_id if proto.order else 0
    position_id = proto.position.position_id if proto.position else None
    symbol_id = proto.order.trade_data.symbol_id if proto.order and proto.order.trade_data else 0

    # Extract deal details
    filled_volume = None
    fill_price = None
    timestamp = datetime.now(UTC)

    if proto.deal:
        filled_volume = proto.deal.filled_volume if proto.deal.filled_volume else None
        if proto.deal.execution_price:
            fill_price = Decimal(str(proto.deal.execution_price))
        if proto.deal.execution_timestamp:
            timestamp = datetime.fromtimestamp(proto.deal.execution_timestamp / 1000, tz=UTC)

    return ExecutionEvent(
        account_id=proto.ctid_trader_account_id,
        execution_type=exec_type,
        order_id=order_id,
        position_id=position_id,
        symbol_id=symbol_id,
        side=side,
        filled_volume=filled_volume,
        fill_price=fill_price,
        timestamp=timestamp,
        is_server_event=proto.is_server_event if proto.is_server_event else False,
        error_code=proto.error_code if proto.error_code else None,
    )


class TradingAPI:
    """Trading operations: orders and positions.

    Provides methods for order placement, modification, cancellation,
    and position management.

    Example:
        ```python
        from ctrader_api_client.models import NewOrderRequest
        from ctrader_api_client.enums import OrderSide, OrderType

        # Place a market order
        request = NewOrderRequest(
            symbol_id=270,
            side=OrderSide.BUY,
            volume=100,  # 0.01 lots
            order_type=OrderType.MARKET,
        )
        execution = await client.trading.place_order(account_id, request)
        print(f"Order {execution.order_id}: {execution.execution_type}")

        # Get open positions
        positions = await client.trading.get_open_positions(account_id)
        for pos in positions:
            print(f"Position {pos.position_id}: {pos.volume} @ {pos.entry_price}")
        ```
    """

    def __init__(self, protocol: Protocol, default_timeout: float = 30.0) -> None:
        """Initialize the trading API.

        Args:
            protocol: The protocol instance for sending requests.
            default_timeout: Default request timeout in seconds.
        """
        self._protocol = protocol
        self._default_timeout = default_timeout

    async def subscribe_to_pnl_changes(self, account_id: int) -> None:
        """Subscribe to PnL change events.

        After subscribing, PnL change data will be delivered via the event system.
        Use `@client.on(PnLChangeEvent)` to handle them.

        Note:
            This subscription seems to be currently rate-limited by cTrader, so it may not work as expected.

        Args:
            account_id: The cTID trader account ID.
        """
        request = ProtoOAv1PnLChangeSubscribeReq(ctid_trader_account_id=account_id)

        response = await self._protocol.send_request(
            request,
            timeout=self._default_timeout,
        )

        if not isinstance(response, ProtoOAv1PnLChangeSubscribeRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOAv1PnLChangeSubscribeRes, got {type(response).__name__}",
            )

    async def place_order(
        self,
        account_id: int,
        request: NewOrderRequest,
        timeout: float | None = None,
    ) -> ExecutionEvent:
        """Place a new order.

        Args:
            account_id: The cTID trader account ID.
            request: Order parameters.
            timeout: Request timeout (uses default if None).

        Returns:
            ExecutionEvent with order details.

        Note:
            For market orders, the order may be immediately filled.
            Check execution_type to determine the outcome:
            - ORDER_ACCEPTED: Pending order created
            - ORDER_FILLED: Order fully executed
            - ORDER_PARTIAL_FILL: Order partially executed
            - ORDER_REJECTED: Order was rejected

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        logger.debug(
            "Placing order: account=%d symbol=%d type=%s volume=%d",
            account_id,
            request.symbol_id,
            request.order_type.name,
            request.volume,
        )
        proto_request = request.to_proto(account_id)

        response = await self._protocol.send_request(
            proto_request,
            timeout=timeout or self._default_timeout,
        )

        _raise_if_order_error(response)

        if not isinstance(response, ProtoOAExecutionEvent):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOAExecutionEvent, got {type(response).__name__}",
            )

        return _proto_to_execution_event(response)

    async def amend_order(
        self,
        account_id: int,
        request: AmendOrderRequest,
        timeout: float | None = None,
    ) -> ExecutionEvent:
        """Modify a pending order.

        Args:
            account_id: The cTID trader account ID.
            request: Amendment parameters.
            timeout: Request timeout (uses default if None).

        Returns:
            ExecutionEvent confirming the amendment.

        Raises:
            APIError: If request fails or order not found.
            CTraderConnectionTimeoutError: If request times out.
        """
        logger.debug("Amending order: account=%d order=%d", account_id, request.order_id)
        proto_request = request.to_proto(account_id)

        response = await self._protocol.send_request(
            proto_request,
            timeout=timeout or self._default_timeout,
        )

        _raise_if_order_error(response)

        if not isinstance(response, ProtoOAExecutionEvent):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOAExecutionEvent, got {type(response).__name__}",
            )

        return _proto_to_execution_event(response)

    async def cancel_order(
        self,
        account_id: int,
        order_id: int,
        timeout: float | None = None,
    ) -> ExecutionEvent:
        """Cancel a pending order.

        Args:
            account_id: The cTID trader account ID.
            order_id: The order to cancel.
            timeout: Request timeout (uses default if None).

        Returns:
            ExecutionEvent confirming cancellation.

        Raises:
            APIError: If request fails or order not found.
            CTraderConnectionTimeoutError: If request times out.
        """
        logger.debug("Cancelling order: account=%d order=%d", account_id, order_id)
        request = ProtoOACancelOrderReq(
            ctid_trader_account_id=account_id,
            order_id=order_id,
        )

        response = await self._protocol.send_request(
            request,
            timeout=timeout or self._default_timeout,
        )

        _raise_if_order_error(response)

        if not isinstance(response, ProtoOAExecutionEvent):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOAExecutionEvent, got {type(response).__name__}",
            )

        return _proto_to_execution_event(response)

    async def close_position(
        self,
        account_id: int,
        request: ClosePositionRequest,
        timeout: float | None = None,
    ) -> ExecutionEvent:
        """Close a position (fully or partially).

        Args:
            account_id: The cTID trader account ID.
            request: Close parameters (position_id and volume required).
            timeout: Request timeout (uses default if None).

        Returns:
            ExecutionEvent with closing details.

        Raises:
            APIError: If request fails or position not found.
            CTraderConnectionTimeoutError: If request times out.
        """
        logger.debug("Closing position: account=%d position=%d", account_id, request.position_id)
        proto_request = request.to_proto(account_id)

        response = await self._protocol.send_request(
            proto_request,
            timeout=timeout or self._default_timeout,
        )

        _raise_if_order_error(response)

        if not isinstance(response, ProtoOAExecutionEvent):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOAExecutionEvent, got {type(response).__name__}",
            )

        return _proto_to_execution_event(response)

    async def amend_position(
        self,
        account_id: int,
        request: AmendPositionRequest,
        timeout: float | None = None,
    ) -> ExecutionEvent:
        """Modify position stop loss and take profit.

        Args:
            account_id: The cTID trader account ID.
            request: Amendment parameters.
            timeout: Request timeout (uses default if None).

        Returns:
            ExecutionEvent confirming the amendment.

        Raises:
            APIError: If request fails or position not found.
            CTraderConnectionTimeoutError: If request times out.
        """
        logger.debug("Amending position: account=%d position=%d", account_id, request.position_id)
        proto_request = request.to_proto(account_id)

        response = await self._protocol.send_request(
            proto_request,
            timeout=timeout or self._default_timeout,
        )

        _raise_if_order_error(response)

        if not isinstance(response, ProtoOAExecutionEvent):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOAExecutionEvent, got {type(response).__name__}",
            )

        return _proto_to_execution_event(response)

    async def get_open_positions(
        self,
        account_id: int,
        timeout: float | None = None,
    ) -> list[Position]:
        """Get all open positions.

        Args:
            account_id: The cTID trader account ID.
            timeout: Request timeout (uses default if None).

        Returns:
            List of open Position objects.

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        request = ProtoOAReconcileReq(ctid_trader_account_id=account_id)

        response = await self._protocol.send_request(
            request,
            timeout=timeout or self._default_timeout,
        )

        if not isinstance(response, ProtoOAReconcileRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOAReconcileRes, got {type(response).__name__}",
            )

        return [Position.from_proto(p) for p in response.position]

    async def get_orders(
        self,
        account_id: int,
        timeout: float | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> list[Order]:
        """Get all orders in a time range.

        Args:
            account_id: The cTID trader account ID.
            timeout: Request timeout (uses default if None).
            from_timestamp: Start of time range (inclusive, optional).
            to_timestamp: End of time range (inclusive, optional).

        Returns:
            List of Order objects in the time range.

        Note:
            If from_timestamp and to_timestamp are not provided, returns all orders.
            The maximum time range may be limited by the server.
            For large ranges, consider paginating with smaller windows.

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        request = ProtoOAOrderListReq(
            ctid_trader_account_id=account_id,
            from_timestamp=int(from_timestamp.timestamp() * 1000) if from_timestamp else None,  # type: ignore [arg-type]
            to_timestamp=int(to_timestamp.timestamp() * 1000) if to_timestamp else None,  # type: ignore [arg-type]
        )

        response = await self._protocol.send_request(
            request,
            timeout=timeout or self._default_timeout,
        )

        if not isinstance(response, ProtoOAOrderListRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOAOrderListRes, got {type(response).__name__}",
            )

        return [Order.from_proto(o) for o in response.order]

    async def get_pending_orders(
        self,
        account_id: int,
        timeout: float | None = None,
    ) -> list[Order]:
        """Get all pending orders.

        Args:
            account_id: The cTID trader account ID.
            timeout: Request timeout (uses default if None).

        Returns:
            List of pending Order objects.

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        request = ProtoOAOrderListReq(ctid_trader_account_id=account_id)

        response = await self._protocol.send_request(
            request,
            timeout=timeout or self._default_timeout,
        )

        if not isinstance(response, ProtoOAOrderListRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOAOrderListRes, got {type(response).__name__}",
            )

        orders = [Order.from_proto(o) for o in response.order]

        pending_orders = [o for o in orders if o.is_pending]

        return pending_orders

    async def get_deals_by_position_id(
        self,
        account_id: int,
        position_id: int,
    ) -> list[Deal]:
        """Get all deals for a specific position.

        Args:
            account_id: The cTID trader account ID.
            position_id: The position ID to filter deals by.

        Returns:
            List of Deal objects associated with the position.

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        request = ProtoOADealListByPositionIdReq(
            ctid_trader_account_id=account_id,
            position_id=position_id,
        )

        response = await self._protocol.send_request(
            request,
            timeout=self._default_timeout,
        )

        if not isinstance(response, ProtoOADealListByPositionIdRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOADealListRes, got {type(response).__name__}",
            )

        return [Deal.from_proto(d) for d in response.deal]

    async def get_deals(
        self,
        account_id: int,
        from_timestamp: datetime,
        to_timestamp: datetime,
        timeout: float | None = None,
    ) -> list[Deal]:
        """Get historical deals.

        Args:
            account_id: The cTID trader account ID.
            from_timestamp: Start of time range (inclusive).
            to_timestamp: End of time range (inclusive).
            timeout: Request timeout (uses default if None).

        Returns:
            List of Deal objects in the time range.

        Note:
            The maximum time range may be limited by the server.
            For large ranges, consider paginating with smaller windows.

        Raises:
            APIError: If request fails.
            CTraderConnectionTimeoutError: If request times out.
        """
        request = ProtoOADealListReq(
            ctid_trader_account_id=account_id,
            from_timestamp=int(from_timestamp.timestamp() * 1000),
            to_timestamp=int(to_timestamp.timestamp() * 1000),
        )

        response = await self._protocol.send_request(
            request,
            timeout=timeout or self._default_timeout,
        )

        if not isinstance(response, ProtoOADealListRes):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected ProtoOADealListRes, got {type(response).__name__}",
            )

        return [Deal.from_proto(d) for d in response.deal]
