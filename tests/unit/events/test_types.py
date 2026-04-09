"""Tests for event type definitions."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ctrader_api_client.events.types import (
    AccountDisconnectEvent,
    ClientDisconnectEvent,
    DepthEvent,
    DepthQuote,
    ExecutionEvent,
    ExecutionType,
    MarginCallTriggerEvent,
    MarginChangeEvent,
    OrderErrorEvent,
    OrderSide,
    PnLChangeEvent,
    SpotEvent,
    SymbolChangedEvent,
    TokenInvalidatedEvent,
    TraderUpdateEvent,
    TrailingStopChangedEvent,
)


class TestSpotEvent:
    """Tests for SpotEvent dataclass."""

    def test_spot_event_creation(self) -> None:
        """Test basic SpotEvent creation."""
        timestamp = datetime.now(UTC)
        event = SpotEvent(
            account_id=123,
            symbol_id=1,
            bid=123000,
            ask=123050,
            timestamp=timestamp,
        )

        assert event.account_id == 123
        assert event.symbol_id == 1
        assert event.bid == 123000
        assert event.ask == 123050
        assert event.timestamp == timestamp

    def test_spot_event_is_frozen(self) -> None:
        """Test that SpotEvent is immutable."""
        event = SpotEvent(
            account_id=123,
            symbol_id=1,
            bid=123000,
            ask=123050,
            timestamp=datetime.now(UTC),
        )

        with pytest.raises(AttributeError):
            event.bid = 124000  # ty: ignore[invalid-assignment]

    def test_spot_event_with_none_values(self) -> None:
        """Test SpotEvent with None bid/ask."""
        event = SpotEvent(
            account_id=123,
            symbol_id=1,
            bid=None,
            ask=None,
            timestamp=datetime.now(UTC),
        )

        assert event.bid is None
        assert event.ask is None


class TestExecutionEvent:
    """Tests for ExecutionEvent dataclass."""

    def test_execution_event_creation(self) -> None:
        """Test basic ExecutionEvent creation."""
        timestamp = datetime.now(UTC)
        event = ExecutionEvent(
            account_id=123,
            execution_type=ExecutionType.ORDER_FILLED,
            order_id=456,
            position_id=789,
            symbol_id=1,
            side=OrderSide.BUY,
            filled_volume=10000,
            fill_price=Decimal("1.23456"),
            timestamp=timestamp,
        )

        assert event.account_id == 123
        assert event.execution_type == ExecutionType.ORDER_FILLED
        assert event.order_id == 456
        assert event.position_id == 789
        assert event.symbol_id == 1
        assert event.side == OrderSide.BUY
        assert event.filled_volume == 10000
        assert event.fill_price == Decimal("1.23456")
        assert event.is_server_event is False
        assert event.error_code is None

    def test_execution_event_with_server_event(self) -> None:
        """Test ExecutionEvent with server event flag."""
        event = ExecutionEvent(
            account_id=123,
            execution_type=ExecutionType.ORDER_CANCELLED,
            order_id=456,
            position_id=None,
            symbol_id=1,
            side=OrderSide.SELL,
            filled_volume=None,
            fill_price=None,
            timestamp=datetime.now(UTC),
            is_server_event=True,
            error_code="STOP_OUT",
        )

        assert event.is_server_event is True
        assert event.error_code == "STOP_OUT"


class TestExecutionTypeEnum:
    """Tests for ExecutionType enum."""

    def test_all_execution_types_present(self) -> None:
        """Test that all execution types are defined."""
        expected = [
            "ORDER_ACCEPTED",
            "ORDER_FILLED",
            "ORDER_REPLACED",
            "ORDER_CANCELLED",
            "ORDER_EXPIRED",
            "ORDER_REJECTED",
            "ORDER_CANCEL_REJECTED",
            "ORDER_PARTIAL_FILL",
            "SWAP",
            "DEPOSIT_WITHDRAW",
            "BONUS_DEPOSIT_WITHDRAW",
        ]
        actual = [e.name for e in ExecutionType]
        for name in expected:
            assert name in actual


class TestOrderSideEnum:
    """Tests for OrderSide enum."""

    def test_order_sides_present(self) -> None:
        """Test that BUY and SELL are defined."""
        assert OrderSide.BUY.value == "BUY"
        assert OrderSide.SELL.value == "SELL"


class TestOrderErrorEvent:
    """Tests for OrderErrorEvent dataclass."""

    def test_order_error_event_creation(self) -> None:
        """Test basic OrderErrorEvent creation."""
        event = OrderErrorEvent(
            account_id=123,
            order_id=456,
            position_id=789,
            error_code="NOT_ENOUGH_MONEY",
            description="Insufficient margin",
        )

        assert event.account_id == 123
        assert event.order_id == 456
        assert event.position_id == 789
        assert event.error_code == "NOT_ENOUGH_MONEY"
        assert event.description == "Insufficient margin"


class TestTraderUpdateEvent:
    """Tests for TraderUpdateEvent dataclass."""

    def test_trader_update_event_creation(self) -> None:
        """Test basic TraderUpdateEvent creation."""
        event = TraderUpdateEvent(
            account_id=123,
            balance=10053099944,
            leverage_in_cents=5000,
            money_digits=8,
        )

        assert event.account_id == 123
        assert event.balance == 10053099944
        assert event.leverage_in_cents == 5000
        assert event.money_digits == 8


class TestMarginChangeEvent:
    """Tests for MarginChangeEvent dataclass."""

    def test_margin_change_event_creation(self) -> None:
        """Test basic MarginChangeEvent creation."""
        event = MarginChangeEvent(
            account_id=123,
            position_id=456,
            used_margin=1000000000,
            money_digits=8,
        )

        assert event.account_id == 123
        assert event.position_id == 456
        assert event.used_margin == 1000000000
        assert event.money_digits == 8


class TestDepthEvent:
    """Tests for DepthEvent dataclass."""

    def test_depth_event_creation(self) -> None:
        """Test basic DepthEvent creation."""
        quotes = (
            DepthQuote(quote_id=1, price=123000, size=100000, is_bid=True),
            DepthQuote(quote_id=2, price=123050, size=50000, is_bid=False),
        )
        event = DepthEvent(
            account_id=123,
            symbol_id=1,
            new_quotes=quotes,
            deleted_quote_ids=(3, 4),
        )

        assert event.account_id == 123
        assert event.symbol_id == 1
        assert len(event.new_quotes) == 2
        assert event.new_quotes[0].is_bid is True
        assert event.new_quotes[1].is_bid is False
        assert event.deleted_quote_ids == (3, 4)


class TestTokenInvalidatedEvent:
    """Tests for TokenInvalidatedEvent dataclass."""

    def test_token_invalidated_event_creation(self) -> None:
        """Test basic TokenInvalidatedEvent creation."""
        event = TokenInvalidatedEvent(
            account_ids=(123, 456),
            reason="Token expired",
        )

        assert event.account_ids == (123, 456)
        assert event.reason == "Token expired"


class TestClientDisconnectEvent:
    """Tests for ClientDisconnectEvent dataclass."""

    def test_client_disconnect_event_creation(self) -> None:
        """Test basic ClientDisconnectEvent creation."""
        event = ClientDisconnectEvent(reason="Server maintenance")

        assert event.reason == "Server maintenance"


class TestAccountDisconnectEvent:
    """Tests for AccountDisconnectEvent dataclass."""

    def test_account_disconnect_event_creation(self) -> None:
        """Test basic AccountDisconnectEvent creation."""
        event = AccountDisconnectEvent(account_id=123)

        assert event.account_id == 123


class TestSymbolChangedEvent:
    """Tests for SymbolChangedEvent dataclass."""

    def test_symbol_changed_event_creation(self) -> None:
        """Test basic SymbolChangedEvent creation."""
        event = SymbolChangedEvent(
            account_id=123,
            symbol_ids=(1, 2, 3),
        )

        assert event.account_id == 123
        assert event.symbol_ids == (1, 2, 3)


class TestTrailingStopChangedEvent:
    """Tests for TrailingStopChangedEvent dataclass."""

    def test_trailing_stop_changed_event_creation(self) -> None:
        """Test basic TrailingStopChangedEvent creation."""
        timestamp = datetime.now(UTC)
        event = TrailingStopChangedEvent(
            account_id=123,
            position_id=456,
            order_id=789,
            stop_price=Decimal("1.23456"),
            timestamp=timestamp,
        )

        assert event.account_id == 123
        assert event.position_id == 456
        assert event.order_id == 789
        assert event.stop_price == Decimal("1.23456")
        assert event.timestamp == timestamp


class TestMarginCallTriggerEvent:
    """Tests for MarginCallTriggerEvent dataclass."""

    def test_margin_call_trigger_event_creation(self) -> None:
        """Test basic MarginCallTriggerEvent creation."""
        event = MarginCallTriggerEvent(
            account_id=123,
            margin_call_type=1,
            margin_level_threshold=Decimal("50.0"),
        )

        assert event.account_id == 123
        assert event.margin_call_type == 1
        assert event.margin_level_threshold == Decimal("50.0")


class TestPnLChangeEvent:
    """Tests for PnLChangeEvent dataclass."""

    def test_pnl_change_event_creation(self) -> None:
        """Test basic PnLChangeEvent creation."""
        event = PnLChangeEvent(
            account_id=123,
            gross_unrealized_pnl=100000000,
            net_unrealized_pnl=95000000,
            money_digits=8,
        )

        assert event.account_id == 123
        assert event.gross_unrealized_pnl == 100000000
        assert event.net_unrealized_pnl == 95000000
        assert event.money_digits == 8
