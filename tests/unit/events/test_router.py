"""Tests for EventRouter."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from ctrader_api_client.enums import ExecutionType, OrderSide
from ctrader_api_client.events.emitter import EventEmitter
from ctrader_api_client.events.router import EventRouter
from ctrader_api_client.events.types import (
    AccountDisconnectEvent,
    ClientDisconnectEvent,
    DepthEvent,
    ExecutionEvent,
    MarginCallTriggerEvent,
    MarginChangeEvent,
    OrderErrorEvent,
    SpotEvent,
    SymbolChangedEvent,
    TokenInvalidatedEvent,
    TraderUpdateEvent,
    TrailingStopChangedEvent,
)


@pytest.fixture
def mock_protocol() -> MagicMock:
    """Create a mock protocol."""
    protocol = MagicMock()
    protocol.on_event = MagicMock()
    protocol.remove_handler = MagicMock()
    return protocol


@pytest.fixture
def emitter() -> EventEmitter:
    """Create an event emitter."""
    return EventEmitter()


@pytest.fixture
def router(mock_protocol: MagicMock, emitter: EventEmitter) -> EventRouter:
    """Create an event router."""
    return EventRouter(mock_protocol, emitter)


class TestEventRouterStartStop:
    """Tests for router start/stop."""

    def test_start_registers_proto_handlers(self, router: EventRouter, mock_protocol: MagicMock) -> None:
        """Test that start registers handlers for all proto event types."""
        router.start()

        # Should register handlers for all event types
        assert mock_protocol.on_event.call_count >= 9
        assert router.is_started is True

    def test_start_is_idempotent(self, router: EventRouter, mock_protocol: MagicMock) -> None:
        """Test that calling start twice doesn't register handlers twice."""
        router.start()
        call_count = mock_protocol.on_event.call_count

        router.start()

        assert mock_protocol.on_event.call_count == call_count

    def test_stop_removes_proto_handlers(self, router: EventRouter, mock_protocol: MagicMock) -> None:
        """Test that stop removes all registered handlers."""
        router.start()
        router.stop()

        assert mock_protocol.remove_handler.call_count >= 9
        assert router.is_started is False

    def test_stop_before_start_does_nothing(self, router: EventRouter, mock_protocol: MagicMock) -> None:
        """Test that stop before start doesn't error."""
        router.stop()

        mock_protocol.remove_handler.assert_not_called()


class TestSpotEventConversion:
    """Tests for SpotEvent conversion."""

    @pytest.mark.anyio
    async def test_spot_event_conversion(self, router: EventRouter, emitter: EventEmitter) -> None:
        """Test that ProtoOASpotEvent is converted correctly."""
        received_events: list[SpotEvent] = []

        async def handler(event: SpotEvent) -> None:
            received_events.append(event)

        emitter.subscribe(SpotEvent, handler)
        router.start()

        # Create mock proto message
        proto = MagicMock()
        proto.ctid_trader_account_id = 123
        proto.symbol_id = 1
        proto.bid = 123000  # Raw value, will be divided by 1e5
        proto.ask = 123050
        proto.timestamp = 1609459200000  # 2021-01-01 00:00:00 UTC
        proto.trendbar = []  # No trendbar

        # Call handler directly
        await router._handle_spot(proto)

        assert len(received_events) == 1
        event = received_events[0]
        assert event.account_id == 123
        assert event.symbol_id == 1
        assert event.bid == 1.23  # 123000 / 1e5
        assert event.ask == 1.2305  # 123050 / 1e5
        assert event.trendbar is None
        assert event.timestamp == datetime(2021, 1, 1, 0, 0, 0, tzinfo=UTC)

    @pytest.mark.anyio
    async def test_spot_event_with_none_prices(self, router: EventRouter, emitter: EventEmitter) -> None:
        """Test SpotEvent with None bid/ask."""
        received_events: list[SpotEvent] = []

        async def handler(event: SpotEvent) -> None:
            received_events.append(event)

        emitter.subscribe(SpotEvent, handler)
        router.start()

        proto = MagicMock()
        proto.ctid_trader_account_id = 123
        proto.symbol_id = 1
        proto.bid = 0  # Zero means None
        proto.ask = 0
        proto.timestamp = 0
        proto.trendbar = []

        await router._handle_spot(proto)

        assert len(received_events) == 1
        assert received_events[0].bid is None
        assert received_events[0].ask is None
        assert received_events[0].trendbar is None


class TestExecutionEventConversion:
    """Tests for ExecutionEvent conversion."""

    @pytest.mark.anyio
    async def test_execution_event_conversion(self, router: EventRouter, emitter: EventEmitter) -> None:
        """Test that ProtoOAExecutionEvent is converted correctly."""
        received_events: list[ExecutionEvent] = []

        async def handler(event: ExecutionEvent) -> None:
            received_events.append(event)

        emitter.subscribe(ExecutionEvent, handler)
        router.start()

        # Create mock proto message
        proto = MagicMock()
        proto.ctid_trader_account_id = 123
        proto.execution_type = 3  # ORDER_FILLED
        proto.is_server_event = False
        proto.error_code = None

        proto.order = MagicMock()
        proto.order.order_id = 456
        proto.order.trade_data = MagicMock()
        proto.order.trade_data.symbol_id = 1
        proto.order.trade_data.trade_side = 1  # BUY

        proto.position = MagicMock()
        proto.position.position_id = 789

        proto.deal = MagicMock()
        proto.deal.filled_volume = 10000
        proto.deal.execution_price = 1.23456
        proto.deal.execution_timestamp = 1609459200000

        await router._handle_execution(proto)

        assert len(received_events) == 1
        event = received_events[0]
        assert event.account_id == 123
        assert event.execution_type == ExecutionType.ORDER_FILLED
        assert event.order_id == 456
        assert event.position_id == 789
        assert event.symbol_id == 1
        assert event.side == OrderSide.BUY
        assert event.filled_volume == 10000
        assert event.fill_price == Decimal("1.23456")

    @pytest.mark.anyio
    async def test_execution_type_mapping(self, router: EventRouter, emitter: EventEmitter) -> None:
        """Test that all execution types are mapped correctly."""
        received_events: list[ExecutionEvent] = []

        async def handler(event: ExecutionEvent) -> None:
            received_events.append(event)

        emitter.subscribe(ExecutionEvent, handler)
        router.start()

        type_mapping = {
            2: ExecutionType.ORDER_ACCEPTED,
            3: ExecutionType.ORDER_FILLED,
            4: ExecutionType.ORDER_REPLACED,
            5: ExecutionType.ORDER_CANCELLED,
            6: ExecutionType.ORDER_EXPIRED,
            7: ExecutionType.ORDER_REJECTED,
            8: ExecutionType.ORDER_CANCEL_REJECTED,
            9: ExecutionType.SWAP,
            10: ExecutionType.DEPOSIT_WITHDRAW,
            11: ExecutionType.ORDER_PARTIAL_FILL,
            12: ExecutionType.BONUS_DEPOSIT_WITHDRAW,
        }

        for proto_type, expected_type in type_mapping.items():
            received_events.clear()

            proto = MagicMock()
            proto.ctid_trader_account_id = 123
            proto.execution_type = proto_type
            proto.order = None
            proto.position = None
            proto.deal = None
            proto.is_server_event = False
            proto.error_code = None

            await router._handle_execution(proto)

            assert received_events[0].execution_type == expected_type

    @pytest.mark.anyio
    async def test_order_side_mapping(self, router: EventRouter, emitter: EventEmitter) -> None:
        """Test that order side is mapped correctly."""
        received_events: list[ExecutionEvent] = []

        async def handler(event: ExecutionEvent) -> None:
            received_events.append(event)

        emitter.subscribe(ExecutionEvent, handler)
        router.start()

        # Test SELL side
        proto = MagicMock()
        proto.ctid_trader_account_id = 123
        proto.execution_type = 3
        proto.order = MagicMock()
        proto.order.order_id = 456
        proto.order.trade_data = MagicMock()
        proto.order.trade_data.symbol_id = 1
        proto.order.trade_data.trade_side = 2  # SELL
        proto.position = None
        proto.deal = None
        proto.is_server_event = False
        proto.error_code = None

        await router._handle_execution(proto)

        assert received_events[0].side == OrderSide.SELL


class TestOrderErrorEventConversion:
    """Tests for OrderErrorEvent conversion."""

    @pytest.mark.anyio
    async def test_order_error_event_conversion(self, router: EventRouter, emitter: EventEmitter) -> None:
        """Test that ProtoOAOrderErrorEvent is converted correctly."""
        received_events: list[OrderErrorEvent] = []

        async def handler(event: OrderErrorEvent) -> None:
            received_events.append(event)

        emitter.subscribe(OrderErrorEvent, handler)
        router.start()

        proto = MagicMock()
        proto.ctid_trader_account_id = 123
        proto.order_id = 456
        proto.position_id = 789
        proto.error_code = "NOT_ENOUGH_MONEY"
        proto.description = "Insufficient margin"

        await router._handle_order_error(proto)

        assert len(received_events) == 1
        event = received_events[0]
        assert event.account_id == 123
        assert event.order_id == 456
        assert event.position_id == 789
        assert event.error_code == "NOT_ENOUGH_MONEY"
        assert event.description == "Insufficient margin"


class TestTraderUpdateEventConversion:
    """Tests for TraderUpdateEvent conversion."""

    @pytest.mark.anyio
    async def test_trader_update_event_conversion(self, router: EventRouter, emitter: EventEmitter) -> None:
        """Test that ProtoOATraderUpdatedEvent is converted correctly."""
        received_events: list[TraderUpdateEvent] = []

        async def handler(event: TraderUpdateEvent) -> None:
            received_events.append(event)

        emitter.subscribe(TraderUpdateEvent, handler)
        router.start()

        proto = MagicMock()
        proto.ctid_trader_account_id = 123
        proto.trader = MagicMock()
        proto.trader.balance = 10053099944
        proto.trader.leverage_in_cents = 5000
        proto.trader.money_digits = 8

        await router._handle_trader_update(proto)

        assert len(received_events) == 1
        event = received_events[0]
        assert event.account_id == 123
        assert event.balance == 10053099944
        assert event.leverage_in_cents == 5000
        assert event.money_digits == 8


class TestMarginChangeEventConversion:
    """Tests for MarginChangeEvent conversion."""

    @pytest.mark.anyio
    async def test_margin_change_event_conversion(self, router: EventRouter, emitter: EventEmitter) -> None:
        """Test that ProtoOAMarginChangedEvent is converted correctly."""
        received_events: list[MarginChangeEvent] = []

        async def handler(event: MarginChangeEvent) -> None:
            received_events.append(event)

        emitter.subscribe(MarginChangeEvent, handler)
        router.start()

        proto = MagicMock()
        proto.ctid_trader_account_id = 123
        proto.position_id = 456
        proto.used_margin = 1000000000
        proto.money_digits = 8

        await router._handle_margin_change(proto)

        assert len(received_events) == 1
        event = received_events[0]
        assert event.account_id == 123
        assert event.position_id == 456
        assert event.used_margin == 1000000000
        assert event.money_digits == 8


class TestDepthEventConversion:
    """Tests for DepthEvent conversion."""

    @pytest.mark.anyio
    async def test_depth_event_conversion(self, router: EventRouter, emitter: EventEmitter) -> None:
        """Test that ProtoOADepthEvent is converted correctly."""
        received_events: list[DepthEvent] = []

        async def handler(event: DepthEvent) -> None:
            received_events.append(event)

        emitter.subscribe(DepthEvent, handler)
        router.start()

        # Create mock quotes
        bid_quote = MagicMock()
        bid_quote.id = 1
        bid_quote.bid = 123000
        bid_quote.ask = 0
        bid_quote.size = 100000

        ask_quote = MagicMock()
        ask_quote.id = 2
        ask_quote.bid = 0
        ask_quote.ask = 123050
        ask_quote.size = 50000

        proto = MagicMock()
        proto.ctid_trader_account_id = 123
        proto.symbol_id = 1
        proto.new_quotes = [bid_quote, ask_quote]
        proto.deleted_quotes = [3, 4]

        await router._handle_depth(proto)

        assert len(received_events) == 1
        event = received_events[0]
        assert event.account_id == 123
        assert event.symbol_id == 1
        assert len(event.new_quotes) == 2
        assert event.new_quotes[0].is_bid is True
        assert event.new_quotes[1].is_bid is False
        assert event.deleted_quote_ids == (3, 4)


class TestTokenInvalidatedEventConversion:
    """Tests for TokenInvalidatedEvent conversion."""

    @pytest.mark.anyio
    async def test_token_invalidated_event_conversion(self, router: EventRouter, emitter: EventEmitter) -> None:
        """Test that ProtoOAAccountsTokenInvalidatedEvent is converted correctly."""
        received_events: list[TokenInvalidatedEvent] = []

        async def handler(event: TokenInvalidatedEvent) -> None:
            received_events.append(event)

        emitter.subscribe(TokenInvalidatedEvent, handler)
        router.start()

        proto = MagicMock()
        proto.ctid_trader_account_ids = [123, 456]
        proto.reason = "Token expired"

        await router._handle_token_invalidated(proto)

        assert len(received_events) == 1
        event = received_events[0]
        assert event.account_ids == (123, 456)
        assert event.reason == "Token expired"


class TestClientDisconnectEventConversion:
    """Tests for ClientDisconnectEvent conversion."""

    @pytest.mark.anyio
    async def test_client_disconnect_event_conversion(self, router: EventRouter, emitter: EventEmitter) -> None:
        """Test that ProtoOAClientDisconnectEvent is converted correctly."""
        received_events: list[ClientDisconnectEvent] = []

        async def handler(event: ClientDisconnectEvent) -> None:
            received_events.append(event)

        emitter.subscribe(ClientDisconnectEvent, handler)
        router.start()

        proto = MagicMock()
        proto.reason = "Server maintenance"

        await router._handle_client_disconnect(proto)

        assert len(received_events) == 1
        assert received_events[0].reason == "Server maintenance"


class TestAccountDisconnectEventConversion:
    """Tests for AccountDisconnectEvent conversion."""

    @pytest.mark.anyio
    async def test_account_disconnect_event_conversion(self, router: EventRouter, emitter: EventEmitter) -> None:
        """Test that ProtoOAAccountDisconnectEvent is converted correctly."""
        received_events: list[AccountDisconnectEvent] = []

        async def handler(event: AccountDisconnectEvent) -> None:
            received_events.append(event)

        emitter.subscribe(AccountDisconnectEvent, handler)
        router.start()

        proto = MagicMock()
        proto.ctid_trader_account_id = 123

        await router._handle_account_disconnect(proto)

        assert len(received_events) == 1
        assert received_events[0].account_id == 123


class TestSymbolChangedEventConversion:
    """Tests for SymbolChangedEvent conversion."""

    @pytest.mark.anyio
    async def test_symbol_changed_event_conversion(self, router: EventRouter, emitter: EventEmitter) -> None:
        """Test that ProtoOASymbolChangedEvent is converted correctly."""
        received_events: list[SymbolChangedEvent] = []

        async def handler(event: SymbolChangedEvent) -> None:
            received_events.append(event)

        emitter.subscribe(SymbolChangedEvent, handler)
        router.start()

        proto = MagicMock()
        proto.ctid_trader_account_id = 123
        proto.symbol_id = [1, 2, 3]

        await router._handle_symbol_changed(proto)

        assert len(received_events) == 1
        event = received_events[0]
        assert event.account_id == 123
        assert event.symbol_ids == (1, 2, 3)


class TestTrailingStopChangedEventConversion:
    """Tests for TrailingStopChangedEvent conversion."""

    @pytest.mark.anyio
    async def test_trailing_stop_changed_event_conversion(self, router: EventRouter, emitter: EventEmitter) -> None:
        """Test that ProtoOATrailingSLChangedEvent is converted correctly."""
        received_events: list[TrailingStopChangedEvent] = []

        async def handler(event: TrailingStopChangedEvent) -> None:
            received_events.append(event)

        emitter.subscribe(TrailingStopChangedEvent, handler)
        router.start()

        proto = MagicMock()
        proto.ctid_trader_account_id = 123
        proto.position_id = 456
        proto.order_id = 789
        proto.stop_price = 1.23456
        proto.utc_last_update_timestamp = 1609459200000

        await router._handle_trailing_stop_changed(proto)

        assert len(received_events) == 1
        event = received_events[0]
        assert event.account_id == 123
        assert event.position_id == 456
        assert event.order_id == 789
        assert event.stop_price == Decimal("1.23456")
        assert event.timestamp == datetime(2021, 1, 1, 0, 0, 0, tzinfo=UTC)


class TestMarginCallTriggerEventConversion:
    """Tests for MarginCallTriggerEvent conversion."""

    @pytest.mark.anyio
    async def test_margin_call_trigger_event_conversion(self, router: EventRouter, emitter: EventEmitter) -> None:
        """Test that ProtoOAMarginCallTriggerEvent is converted correctly."""
        received_events: list[MarginCallTriggerEvent] = []

        async def handler(event: MarginCallTriggerEvent) -> None:
            received_events.append(event)

        emitter.subscribe(MarginCallTriggerEvent, handler)
        router.start()

        proto = MagicMock()
        proto.ctid_trader_account_id = 123
        proto.margin_call = MagicMock()
        proto.margin_call.margin_call_type = 1
        proto.margin_call.margin_level_threshold = 50.0

        await router._handle_margin_call_trigger(proto)

        assert len(received_events) == 1
        event = received_events[0]
        assert event.account_id == 123
        assert event.margin_call_type == 1
        assert event.margin_level_threshold == Decimal("50.0")


class TestTimestampConversion:
    """Tests for timestamp conversion."""

    def test_timestamp_conversion(self, router: EventRouter) -> None:
        """Test millisecond timestamp to datetime conversion."""
        # 2021-01-01 00:00:00 UTC
        timestamp_ms = 1609459200000

        result = router._timestamp_to_datetime(timestamp_ms)

        assert result == datetime(2021, 1, 1, 0, 0, 0, tzinfo=UTC)

    def test_timestamp_conversion_with_milliseconds(self, router: EventRouter) -> None:
        """Test timestamp conversion preserves milliseconds."""
        # 2021-01-01 00:00:00.500 UTC
        timestamp_ms = 1609459200500

        result = router._timestamp_to_datetime(timestamp_ms)

        assert result.microsecond == 500000
