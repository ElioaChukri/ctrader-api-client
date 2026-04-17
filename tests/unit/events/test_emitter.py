"""Tests for EventEmitter."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from ctrader_api_client.events.emitter import EventEmitter
from ctrader_api_client.events.types import ExecutionEvent, SpotEvent


class TestEventEmitterSubscription:
    """Tests for subscription management."""

    def test_subscribe_registers_handler(self) -> None:
        """Test that subscribe registers a handler."""
        emitter = EventEmitter()
        handler = AsyncMock()

        emitter.subscribe(SpotEvent, handler)

        assert emitter.subscription_count(SpotEvent) == 1

    def test_subscribe_with_account_filter(self) -> None:
        """Test that subscribe stores account filter."""
        emitter = EventEmitter()
        handler = AsyncMock()

        emitter.subscribe(SpotEvent, handler, account_id=123)

        assert emitter.subscription_count(SpotEvent) == 1

    def test_subscribe_with_symbol_filter(self) -> None:
        """Test that subscribe stores symbol filter."""
        emitter = EventEmitter()
        handler = AsyncMock()

        emitter.subscribe(SpotEvent, handler, symbol_id=1)

        assert emitter.subscription_count(SpotEvent) == 1

    def test_subscribe_with_both_filters(self) -> None:
        """Test that subscribe stores both filters."""
        emitter = EventEmitter()
        handler = AsyncMock()

        emitter.subscribe(SpotEvent, handler, account_id=123, symbol_id=1)

        assert emitter.subscription_count(SpotEvent) == 1

    def test_subscribe_multiple_handlers(self) -> None:
        """Test subscribing multiple handlers to same event type."""
        emitter = EventEmitter()
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        emitter.subscribe(SpotEvent, handler1)
        emitter.subscribe(SpotEvent, handler2)

        assert emitter.subscription_count(SpotEvent) == 2

    def test_subscribe_different_event_types(self) -> None:
        """Test subscribing to different event types."""
        emitter = EventEmitter()
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        emitter.subscribe(SpotEvent, handler1)
        emitter.subscribe(ExecutionEvent, handler2)

        assert emitter.subscription_count(SpotEvent) == 1
        assert emitter.subscription_count(ExecutionEvent) == 1
        assert emitter.subscription_count() == 2


class TestEventEmitterUnsubscription:
    """Tests for unsubscription."""

    def test_unsubscribe_removes_handler(self) -> None:
        """Test that unsubscribe removes a handler."""
        emitter = EventEmitter()
        handler = AsyncMock()

        emitter.subscribe(SpotEvent, handler)
        result = emitter.unsubscribe(SpotEvent, handler)

        assert result is True
        assert emitter.subscription_count(SpotEvent) == 0

    def test_unsubscribe_returns_false_if_not_found(self) -> None:
        """Test that unsubscribe returns False if handler not found."""
        emitter = EventEmitter()
        handler = AsyncMock()

        result = emitter.unsubscribe(SpotEvent, handler)

        assert result is False

    def test_unsubscribe_all_clears_type(self) -> None:
        """Test that unsubscribe_all clears a specific type."""
        emitter = EventEmitter()
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        emitter.subscribe(SpotEvent, handler1)
        emitter.subscribe(SpotEvent, handler2)
        emitter.subscribe(ExecutionEvent, handler1)

        count = emitter.unsubscribe_all(SpotEvent)

        assert count == 2
        assert emitter.subscription_count(SpotEvent) == 0
        assert emitter.subscription_count(ExecutionEvent) == 1

    def test_unsubscribe_all_clears_everything(self) -> None:
        """Test that unsubscribe_all with no args clears all handlers."""
        emitter = EventEmitter()
        handler = AsyncMock()

        emitter.subscribe(SpotEvent, handler)
        emitter.subscribe(ExecutionEvent, handler)

        count = emitter.unsubscribe_all()

        assert count == 2
        assert emitter.subscription_count() == 0


class TestEventEmitterEmit:
    """Tests for event emission."""

    @pytest.mark.anyio
    async def test_emit_calls_matching_handlers(self) -> None:
        """Test that emit calls handlers for matching event type."""
        emitter = EventEmitter()
        handler = AsyncMock()

        emitter.subscribe(SpotEvent, handler)

        event = SpotEvent(
            account_id=123,
            symbol_id=1,
            bid=1.23000,
            ask=1.23050,
            trendbar=None,
            timestamp=datetime.now(UTC),
        )
        await emitter.emit(event)

        handler.assert_called_once_with(event)

    @pytest.mark.anyio
    async def test_emit_filters_by_account_id(self) -> None:
        """Test that emit filters events by account_id."""
        emitter = EventEmitter()
        handler = AsyncMock()

        emitter.subscribe(SpotEvent, handler, account_id=123)

        # This event should not match
        event = SpotEvent(
            account_id=456,
            symbol_id=1,
            bid=1.23000,
            ask=1.23050,
            trendbar=None,
            timestamp=datetime.now(UTC),
        )
        await emitter.emit(event)

        handler.assert_not_called()

    @pytest.mark.anyio
    async def test_emit_filters_by_symbol_id(self) -> None:
        """Test that emit filters events by symbol_id."""
        emitter = EventEmitter()
        handler = AsyncMock()

        emitter.subscribe(SpotEvent, handler, symbol_id=1)

        # This event should not match
        event = SpotEvent(
            account_id=123,
            symbol_id=2,
            bid=1.23000,
            ask=1.23050,
            trendbar=None,
            timestamp=datetime.now(UTC),
        )
        await emitter.emit(event)

        handler.assert_not_called()

    @pytest.mark.anyio
    async def test_emit_matches_when_filters_pass(self) -> None:
        """Test that emit calls handler when filters match."""
        emitter = EventEmitter()
        handler = AsyncMock()

        emitter.subscribe(SpotEvent, handler, account_id=123, symbol_id=1)

        event = SpotEvent(
            account_id=123,
            symbol_id=1,
            bid=1.23000,
            ask=1.23050,
            trendbar=None,
            timestamp=datetime.now(UTC),
        )
        await emitter.emit(event)

        handler.assert_called_once_with(event)

    @pytest.mark.anyio
    async def test_emit_calls_handlers_sequentially(self) -> None:
        """Test that handlers are called in registration order."""
        emitter = EventEmitter()
        call_order: list[int] = []

        async def handler1(_event: SpotEvent) -> None:
            call_order.append(1)

        async def handler2(_event: SpotEvent) -> None:
            call_order.append(2)

        async def handler3(_event: SpotEvent) -> None:
            call_order.append(3)

        emitter.subscribe(SpotEvent, handler1)
        emitter.subscribe(SpotEvent, handler2)
        emitter.subscribe(SpotEvent, handler3)

        event = SpotEvent(
            account_id=123,
            symbol_id=1,
            bid=1.23000,
            ask=1.23050,
            trendbar=None,
            timestamp=datetime.now(UTC),
        )
        await emitter.emit(event)

        assert call_order == [1, 2, 3]


class TestEventEmitterErrorHandling:
    """Tests for error handling in event emission."""

    @pytest.mark.anyio
    async def test_emit_continues_after_handler_error(self) -> None:
        """Test that other handlers run even if one fails."""
        emitter = EventEmitter()
        handler1 = AsyncMock(side_effect=ValueError("test error"))
        handler2 = AsyncMock()

        emitter.subscribe(SpotEvent, handler1)
        emitter.subscribe(SpotEvent, handler2)

        event = SpotEvent(
            account_id=123,
            symbol_id=1,
            bid=1.23000,
            ask=1.23050,
            trendbar=None,
            timestamp=datetime.now(UTC),
        )
        await emitter.emit(event)

        handler1.assert_called_once()
        handler2.assert_called_once()

    @pytest.mark.anyio
    async def test_emit_calls_error_callback(self) -> None:
        """Test that error callback is invoked on handler error."""
        error_callback = AsyncMock()
        emitter = EventEmitter(on_handler_error=error_callback)

        error = ValueError("test error")
        handler = AsyncMock(side_effect=error)

        emitter.subscribe(SpotEvent, handler)

        event = SpotEvent(
            account_id=123,
            symbol_id=1,
            bid=1.23000,
            ask=1.23050,
            trendbar=None,
            timestamp=datetime.now(UTC),
        )
        await emitter.emit(event)

        error_callback.assert_called_once()
        call_args = error_callback.call_args[0]
        assert call_args[0] == event
        assert call_args[1] == handler
        assert call_args[2] == error

    @pytest.mark.anyio
    async def test_error_callback_error_is_logged(self) -> None:
        """Test that errors in error callback don't crash emitter."""
        error_callback = AsyncMock(side_effect=RuntimeError("callback error"))
        emitter = EventEmitter(on_handler_error=error_callback)

        handler = AsyncMock(side_effect=ValueError("handler error"))
        emitter.subscribe(SpotEvent, handler)

        event = SpotEvent(
            account_id=123,
            symbol_id=1,
            bid=1.23000,
            ask=1.23050,
            trendbar=None,
            timestamp=datetime.now(UTC),
        )

        # Should not raise
        await emitter.emit(event)

        error_callback.assert_called_once()


class TestEventEmitterSubscriptionCount:
    """Tests for subscription_count method."""

    def test_subscription_count_for_type(self) -> None:
        """Test subscription count for a specific type."""
        emitter = EventEmitter()
        handler = AsyncMock()

        emitter.subscribe(SpotEvent, handler)
        emitter.subscribe(SpotEvent, handler)

        assert emitter.subscription_count(SpotEvent) == 2

    def test_subscription_count_total(self) -> None:
        """Test total subscription count."""
        emitter = EventEmitter()
        handler = AsyncMock()

        emitter.subscribe(SpotEvent, handler)
        emitter.subscribe(ExecutionEvent, handler)

        assert emitter.subscription_count() == 2

    def test_subscription_count_empty(self) -> None:
        """Test subscription count when empty."""
        emitter = EventEmitter()

        assert emitter.subscription_count() == 0
        assert emitter.subscription_count(SpotEvent) == 0
