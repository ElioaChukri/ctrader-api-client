"""Message routing and request correlation."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import betterproto

from ..exceptions import DeserializationError, UnknownPayloadTypeError
from .proto import (
    ProtoErrorRes,
    ProtoHeartbeatEvent,
    ProtoMessage,
    ProtoOAAccountAuthReq,
    ProtoOAAccountAuthRes,
    ProtoOAAccountDisconnectEvent,
    ProtoOAAccountLogoutReq,
    ProtoOAAccountLogoutRes,
    ProtoOAAccountsTokenInvalidatedEvent,
    ProtoOAAmendOrderReq,
    ProtoOAAmendPositionSLTPReq,
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAAssetClassListReq,
    ProtoOAAssetClassListRes,
    ProtoOAAssetListReq,
    ProtoOAAssetListRes,
    ProtoOACancelOrderReq,
    ProtoOACashFlowHistoryListReq,
    ProtoOACashFlowHistoryListRes,
    ProtoOAClientDisconnectEvent,
    ProtoOAClosePositionReq,
    ProtoOADealListByPositionIdReq,
    ProtoOADealListByPositionIdRes,
    ProtoOADealListReq,
    ProtoOADealListRes,
    ProtoOADealOffsetListReq,
    ProtoOADealOffsetListRes,
    ProtoOADepthEvent,
    ProtoOAErrorRes,
    ProtoOAExecutionEvent,
    ProtoOAExpectedMarginReq,
    ProtoOAExpectedMarginRes,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAGetAccountListByAccessTokenRes,
    ProtoOAGetCtidProfileByTokenReq,
    ProtoOAGetCtidProfileByTokenRes,
    ProtoOAGetDynamicLeverageByIDReq,
    ProtoOAGetDynamicLeverageByIDRes,
    ProtoOAGetPositionUnrealizedPnLReq,
    ProtoOAGetPositionUnrealizedPnLRes,
    ProtoOAGetTickDataReq,
    ProtoOAGetTickDataRes,
    ProtoOAGetTrendbarsReq,
    ProtoOAGetTrendbarsRes,
    ProtoOAMarginCallListReq,
    ProtoOAMarginCallListRes,
    ProtoOAMarginCallTriggerEvent,
    ProtoOAMarginCallUpdateEvent,
    ProtoOAMarginCallUpdateReq,
    ProtoOAMarginCallUpdateRes,
    ProtoOAMarginChangedEvent,
    ProtoOANewOrderReq,
    ProtoOAOrderDetailsReq,
    ProtoOAOrderDetailsRes,
    ProtoOAOrderErrorEvent,
    ProtoOAOrderListByPositionIdReq,
    ProtoOAOrderListByPositionIdRes,
    ProtoOAOrderListReq,
    ProtoOAOrderListRes,
    ProtoOAPayloadType,
    ProtoOAReconcileReq,
    ProtoOAReconcileRes,
    ProtoOARefreshTokenReq,
    ProtoOARefreshTokenRes,
    ProtoOASpotEvent,
    ProtoOASubscribeDepthQuotesReq,
    ProtoOASubscribeDepthQuotesRes,
    ProtoOASubscribeLiveTrendbarReq,
    ProtoOASubscribeLiveTrendbarRes,
    ProtoOASubscribeSpotsReq,
    ProtoOASubscribeSpotsRes,
    ProtoOASymbolByIdReq,
    ProtoOASymbolByIdRes,
    ProtoOASymbolCategoryListReq,
    ProtoOASymbolCategoryListRes,
    ProtoOASymbolChangedEvent,
    ProtoOASymbolsForConversionReq,
    ProtoOASymbolsForConversionRes,
    ProtoOASymbolsListReq,
    ProtoOASymbolsListRes,
    ProtoOATraderReq,
    ProtoOATraderRes,
    ProtoOATraderUpdatedEvent,
    ProtoOATrailingSLChangedEvent,
    ProtoOAUnsubscribeDepthQuotesReq,
    ProtoOAUnsubscribeDepthQuotesRes,
    ProtoOAUnsubscribeLiveTrendbarReq,
    ProtoOAUnsubscribeLiveTrendbarRes,
    ProtoOAUnsubscribeSpotsReq,
    ProtoOAUnsubscribeSpotsRes,
    ProtoOAv1PnLChangeEvent,
    ProtoOAv1PnLChangeSubscribeReq,
    ProtoOAv1PnLChangeSubscribeRes,
    ProtoOAv1PnLChangeUnSubscribeReq,
    ProtoOAv1PnLChangeUnSubscribeRes,
    ProtoOAVersionReq,
    ProtoOAVersionRes,
    ProtoPayloadType,
)


# Explicit mapping from payload type to message class.
# This is intentionally manual to catch any mismatches at import time.
_PAYLOAD_TYPE_TO_CLASS: dict[int, type[betterproto.Message]] = {
    # Common messages
    ProtoPayloadType.ERROR_RES: ProtoErrorRes,
    ProtoPayloadType.HEARTBEAT_EVENT: ProtoHeartbeatEvent,
    # OpenAPI messages
    ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_REQ: ProtoOAApplicationAuthReq,
    ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_RES: ProtoOAApplicationAuthRes,
    ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_REQ: ProtoOAAccountAuthReq,
    ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_RES: ProtoOAAccountAuthRes,
    ProtoOAPayloadType.PROTO_OA_VERSION_REQ: ProtoOAVersionReq,
    ProtoOAPayloadType.PROTO_OA_VERSION_RES: ProtoOAVersionRes,
    ProtoOAPayloadType.PROTO_OA_NEW_ORDER_REQ: ProtoOANewOrderReq,
    ProtoOAPayloadType.PROTO_OA_TRAILING_SL_CHANGED_EVENT: ProtoOATrailingSLChangedEvent,
    ProtoOAPayloadType.PROTO_OA_CANCEL_ORDER_REQ: ProtoOACancelOrderReq,
    ProtoOAPayloadType.PROTO_OA_AMEND_ORDER_REQ: ProtoOAAmendOrderReq,
    ProtoOAPayloadType.PROTO_OA_AMEND_POSITION_SLTP_REQ: ProtoOAAmendPositionSLTPReq,
    ProtoOAPayloadType.PROTO_OA_CLOSE_POSITION_REQ: ProtoOAClosePositionReq,
    ProtoOAPayloadType.PROTO_OA_ASSET_LIST_REQ: ProtoOAAssetListReq,
    ProtoOAPayloadType.PROTO_OA_ASSET_LIST_RES: ProtoOAAssetListRes,
    ProtoOAPayloadType.PROTO_OA_SYMBOLS_LIST_REQ: ProtoOASymbolsListReq,
    ProtoOAPayloadType.PROTO_OA_SYMBOLS_LIST_RES: ProtoOASymbolsListRes,
    ProtoOAPayloadType.PROTO_OA_SYMBOL_BY_ID_REQ: ProtoOASymbolByIdReq,
    ProtoOAPayloadType.PROTO_OA_SYMBOL_BY_ID_RES: ProtoOASymbolByIdRes,
    ProtoOAPayloadType.PROTO_OA_SYMBOLS_FOR_CONVERSION_REQ: ProtoOASymbolsForConversionReq,
    ProtoOAPayloadType.PROTO_OA_SYMBOLS_FOR_CONVERSION_RES: ProtoOASymbolsForConversionRes,
    ProtoOAPayloadType.PROTO_OA_SYMBOL_CHANGED_EVENT: ProtoOASymbolChangedEvent,
    ProtoOAPayloadType.PROTO_OA_TRADER_REQ: ProtoOATraderReq,
    ProtoOAPayloadType.PROTO_OA_TRADER_RES: ProtoOATraderRes,
    ProtoOAPayloadType.PROTO_OA_TRADER_UPDATE_EVENT: ProtoOATraderUpdatedEvent,
    ProtoOAPayloadType.PROTO_OA_RECONCILE_REQ: ProtoOAReconcileReq,
    ProtoOAPayloadType.PROTO_OA_RECONCILE_RES: ProtoOAReconcileRes,
    ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT: ProtoOAExecutionEvent,
    ProtoOAPayloadType.PROTO_OA_SUBSCRIBE_SPOTS_REQ: ProtoOASubscribeSpotsReq,
    ProtoOAPayloadType.PROTO_OA_SUBSCRIBE_SPOTS_RES: ProtoOASubscribeSpotsRes,
    ProtoOAPayloadType.PROTO_OA_UNSUBSCRIBE_SPOTS_REQ: ProtoOAUnsubscribeSpotsReq,
    ProtoOAPayloadType.PROTO_OA_UNSUBSCRIBE_SPOTS_RES: ProtoOAUnsubscribeSpotsRes,
    ProtoOAPayloadType.PROTO_OA_SPOT_EVENT: ProtoOASpotEvent,
    ProtoOAPayloadType.PROTO_OA_ORDER_ERROR_EVENT: ProtoOAOrderErrorEvent,
    ProtoOAPayloadType.PROTO_OA_DEAL_LIST_REQ: ProtoOADealListReq,
    ProtoOAPayloadType.PROTO_OA_DEAL_LIST_RES: ProtoOADealListRes,
    ProtoOAPayloadType.PROTO_OA_SUBSCRIBE_LIVE_TRENDBAR_REQ: ProtoOASubscribeLiveTrendbarReq,
    ProtoOAPayloadType.PROTO_OA_UNSUBSCRIBE_LIVE_TRENDBAR_REQ: ProtoOAUnsubscribeLiveTrendbarReq,
    ProtoOAPayloadType.PROTO_OA_GET_TRENDBARS_REQ: ProtoOAGetTrendbarsReq,
    ProtoOAPayloadType.PROTO_OA_GET_TRENDBARS_RES: ProtoOAGetTrendbarsRes,
    ProtoOAPayloadType.PROTO_OA_EXPECTED_MARGIN_REQ: ProtoOAExpectedMarginReq,
    ProtoOAPayloadType.PROTO_OA_EXPECTED_MARGIN_RES: ProtoOAExpectedMarginRes,
    ProtoOAPayloadType.PROTO_OA_MARGIN_CHANGED_EVENT: ProtoOAMarginChangedEvent,
    ProtoOAPayloadType.PROTO_OA_ERROR_RES: ProtoOAErrorRes,
    ProtoOAPayloadType.PROTO_OA_CASH_FLOW_HISTORY_LIST_REQ: ProtoOACashFlowHistoryListReq,
    ProtoOAPayloadType.PROTO_OA_CASH_FLOW_HISTORY_LIST_RES: ProtoOACashFlowHistoryListRes,
    ProtoOAPayloadType.PROTO_OA_GET_TICKDATA_REQ: ProtoOAGetTickDataReq,
    ProtoOAPayloadType.PROTO_OA_GET_TICKDATA_RES: ProtoOAGetTickDataRes,
    ProtoOAPayloadType.PROTO_OA_ACCOUNTS_TOKEN_INVALIDATED_EVENT: ProtoOAAccountsTokenInvalidatedEvent,
    ProtoOAPayloadType.PROTO_OA_CLIENT_DISCONNECT_EVENT: ProtoOAClientDisconnectEvent,
    ProtoOAPayloadType.PROTO_OA_GET_ACCOUNTS_BY_ACCESS_TOKEN_REQ: ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAPayloadType.PROTO_OA_GET_ACCOUNTS_BY_ACCESS_TOKEN_RES: ProtoOAGetAccountListByAccessTokenRes,
    ProtoOAPayloadType.PROTO_OA_GET_CTID_PROFILE_BY_TOKEN_REQ: ProtoOAGetCtidProfileByTokenReq,
    ProtoOAPayloadType.PROTO_OA_GET_CTID_PROFILE_BY_TOKEN_RES: ProtoOAGetCtidProfileByTokenRes,
    ProtoOAPayloadType.PROTO_OA_ASSET_CLASS_LIST_REQ: ProtoOAAssetClassListReq,
    ProtoOAPayloadType.PROTO_OA_ASSET_CLASS_LIST_RES: ProtoOAAssetClassListRes,
    ProtoOAPayloadType.PROTO_OA_DEPTH_EVENT: ProtoOADepthEvent,
    ProtoOAPayloadType.PROTO_OA_SUBSCRIBE_DEPTH_QUOTES_REQ: ProtoOASubscribeDepthQuotesReq,
    ProtoOAPayloadType.PROTO_OA_SUBSCRIBE_DEPTH_QUOTES_RES: ProtoOASubscribeDepthQuotesRes,
    ProtoOAPayloadType.PROTO_OA_UNSUBSCRIBE_DEPTH_QUOTES_REQ: ProtoOAUnsubscribeDepthQuotesReq,
    ProtoOAPayloadType.PROTO_OA_UNSUBSCRIBE_DEPTH_QUOTES_RES: ProtoOAUnsubscribeDepthQuotesRes,
    ProtoOAPayloadType.PROTO_OA_SYMBOL_CATEGORY_REQ: ProtoOASymbolCategoryListReq,
    ProtoOAPayloadType.PROTO_OA_SYMBOL_CATEGORY_RES: ProtoOASymbolCategoryListRes,
    ProtoOAPayloadType.PROTO_OA_ACCOUNT_LOGOUT_REQ: ProtoOAAccountLogoutReq,
    ProtoOAPayloadType.PROTO_OA_ACCOUNT_LOGOUT_RES: ProtoOAAccountLogoutRes,
    ProtoOAPayloadType.PROTO_OA_ACCOUNT_DISCONNECT_EVENT: ProtoOAAccountDisconnectEvent,
    ProtoOAPayloadType.PROTO_OA_SUBSCRIBE_LIVE_TRENDBAR_RES: ProtoOASubscribeLiveTrendbarRes,
    ProtoOAPayloadType.PROTO_OA_UNSUBSCRIBE_LIVE_TRENDBAR_RES: ProtoOAUnsubscribeLiveTrendbarRes,
    ProtoOAPayloadType.PROTO_OA_MARGIN_CALL_LIST_REQ: ProtoOAMarginCallListReq,
    ProtoOAPayloadType.PROTO_OA_MARGIN_CALL_LIST_RES: ProtoOAMarginCallListRes,
    ProtoOAPayloadType.PROTO_OA_MARGIN_CALL_UPDATE_REQ: ProtoOAMarginCallUpdateReq,
    ProtoOAPayloadType.PROTO_OA_MARGIN_CALL_UPDATE_RES: ProtoOAMarginCallUpdateRes,
    ProtoOAPayloadType.PROTO_OA_MARGIN_CALL_UPDATE_EVENT: ProtoOAMarginCallUpdateEvent,
    ProtoOAPayloadType.PROTO_OA_MARGIN_CALL_TRIGGER_EVENT: ProtoOAMarginCallTriggerEvent,
    ProtoOAPayloadType.PROTO_OA_REFRESH_TOKEN_REQ: ProtoOARefreshTokenReq,
    ProtoOAPayloadType.PROTO_OA_REFRESH_TOKEN_RES: ProtoOARefreshTokenRes,
    ProtoOAPayloadType.PROTO_OA_ORDER_LIST_REQ: ProtoOAOrderListReq,
    ProtoOAPayloadType.PROTO_OA_ORDER_LIST_RES: ProtoOAOrderListRes,
    ProtoOAPayloadType.PROTO_OA_GET_DYNAMIC_LEVERAGE_REQ: ProtoOAGetDynamicLeverageByIDReq,
    ProtoOAPayloadType.PROTO_OA_GET_DYNAMIC_LEVERAGE_RES: ProtoOAGetDynamicLeverageByIDRes,
    ProtoOAPayloadType.PROTO_OA_DEAL_LIST_BY_POSITION_ID_REQ: ProtoOADealListByPositionIdReq,
    ProtoOAPayloadType.PROTO_OA_DEAL_LIST_BY_POSITION_ID_RES: ProtoOADealListByPositionIdRes,
    ProtoOAPayloadType.PROTO_OA_ORDER_DETAILS_REQ: ProtoOAOrderDetailsReq,
    ProtoOAPayloadType.PROTO_OA_ORDER_DETAILS_RES: ProtoOAOrderDetailsRes,
    ProtoOAPayloadType.PROTO_OA_ORDER_LIST_BY_POSITION_ID_REQ: ProtoOAOrderListByPositionIdReq,
    ProtoOAPayloadType.PROTO_OA_ORDER_LIST_BY_POSITION_ID_RES: ProtoOAOrderListByPositionIdRes,
    ProtoOAPayloadType.PROTO_OA_DEAL_OFFSET_LIST_REQ: ProtoOADealOffsetListReq,
    ProtoOAPayloadType.PROTO_OA_DEAL_OFFSET_LIST_RES: ProtoOADealOffsetListRes,
    ProtoOAPayloadType.PROTO_OA_GET_POSITION_UNREALIZED_PNL_REQ: ProtoOAGetPositionUnrealizedPnLReq,
    ProtoOAPayloadType.PROTO_OA_GET_POSITION_UNREALIZED_PNL_RES: ProtoOAGetPositionUnrealizedPnLRes,
    ProtoOAPayloadType.PROTO_OA_V1_PNL_CHANGE_EVENT: ProtoOAv1PnLChangeEvent,
    ProtoOAPayloadType.PROTO_OA_V1_PNL_CHANGE_SUBSCRIBE_REQ: ProtoOAv1PnLChangeSubscribeReq,
    ProtoOAPayloadType.PROTO_OA_V1_PNL_CHANGE_SUBSCRIBE_RES: ProtoOAv1PnLChangeSubscribeRes,
    ProtoOAPayloadType.PROTO_OA_V1_PNL_CHANGE_UN_SUBSCRIBE_REQ: ProtoOAv1PnLChangeUnSubscribeReq,
    ProtoOAPayloadType.PROTO_OA_V1_PNL_CHANGE_UN_SUBSCRIBE_RES: ProtoOAv1PnLChangeUnSubscribeRes,
}


@dataclass
class MessageRegistry:
    """Bidirectional mapping between payload_type and message class."""

    payload_type_to_class: dict[int, type[betterproto.Message]] = field(default_factory=dict)
    class_to_payload_type: dict[type[betterproto.Message], int] = field(default_factory=dict)

    def get_class(self, payload_type: int) -> type[betterproto.Message] | None:
        """Get the message class for a payload type."""
        return self.payload_type_to_class.get(payload_type)

    def get_payload_type(self, cls: type[betterproto.Message]) -> int | None:
        """Get the payload type for a message class."""
        return self.class_to_payload_type.get(cls)

    def register(self, payload_type: int, cls: type[betterproto.Message]) -> None:
        """Register a bidirectional mapping."""
        self.payload_type_to_class[payload_type] = cls
        self.class_to_payload_type[cls] = payload_type


class ClientMessageIdGenerator:
    """Thread-safe incrementing ID generator for request correlation."""

    def __init__(self) -> None:
        self._counter = 0
        self._lock = threading.Lock()

    def next_id(self) -> str:
        """Generate the next unique client message ID."""
        with self._lock:
            self._counter += 1
            return str(self._counter)


# Module-level singleton
_registry: MessageRegistry | None = None
_registry_lock = threading.Lock()


def _build_registry() -> MessageRegistry:
    """Build the message registry from the explicit mapping."""
    registry = MessageRegistry()
    for payload_type, cls in _PAYLOAD_TYPE_TO_CLASS.items():
        registry.register(payload_type, cls)
    return registry


def get_registry() -> MessageRegistry:
    """Get the lazily-initialized singleton registry."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = _build_registry()
    return _registry


def wrap_message(inner: betterproto.Message, client_msg_id: str | None = None) -> ProtoMessage:
    """Wrap an inner message into a ProtoMessage for transmission.

    Args:
        inner: The inner protobuf message to wrap.
        client_msg_id: Optional client message ID for request correlation.

    Returns:
        A ProtoMessage wrapper containing the serialized inner message.

    Raises:
        UnknownPayloadTypeError: If the inner message type is not registered.
    """
    registry = get_registry()
    payload_type = registry.get_payload_type(type(inner))

    if payload_type is None:
        raise UnknownPayloadTypeError(payload_type=-1)

    return ProtoMessage(
        payload_type=payload_type,
        payload=bytes(inner),
        client_msg_id=client_msg_id or "",
    )


def unwrap_message(proto_message: ProtoMessage) -> betterproto.Message:
    """Deserialize the inner payload from a ProtoMessage.

    Args:
        proto_message: The ProtoMessage wrapper to unwrap.

    Returns:
        The deserialized inner message.

    Raises:
        UnknownPayloadTypeError: If the payload type is not registered.
        DeserializationError: If deserialization fails.
    """
    registry = get_registry()
    cls = registry.get_class(proto_message.payload_type)

    if cls is None:
        raise UnknownPayloadTypeError(proto_message.payload_type)

    try:
        return cls().parse(proto_message.payload)
    except Exception as e:
        raise DeserializationError(
            payload_type=proto_message.payload_type,
            raw_data=proto_message.payload,
        ) from e


def deserialize_proto_message(data: bytes) -> ProtoMessage:
    """Deserialize raw bytes to a ProtoMessage wrapper.

    Args:
        data: Raw bytes to deserialize.

    Returns:
        The deserialized ProtoMessage.

    Raises:
        DeserializationError: If deserialization fails.
    """
    try:
        return ProtoMessage().parse(data)
    except Exception as e:
        raise DeserializationError(
            payload_type=-1,
            raw_data=data,
        ) from e
