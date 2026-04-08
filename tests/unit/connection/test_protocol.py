"""Tests for the Protocol class."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import anyio
import pytest

from ctrader_api_client._internal.proto import (
    ProtoHeartbeatEvent,
    ProtoMessage,
    ProtoOAErrorRes,
    ProtoOAVersionReq,
    ProtoOAVersionRes,
    ProtoPayloadType,
)
from ctrader_api_client.connection.protocol import Protocol
from ctrader_api_client.connection.transport import Transport
from ctrader_api_client.exceptions import (
    APIError,
    CTraderConnectionClosedError,
    CTraderConnectionTimeoutError,
)


@pytest.fixture
def mock_transport() -> MagicMock:
    """Create a mock transport."""
    transport = MagicMock(spec=Transport)
    transport.is_connected = True
    transport.send = AsyncMock()
    transport.close = AsyncMock()
    transport.connect = AsyncMock()
    return transport


class TestProtocolInit:
    """Tests for Protocol initialization."""

    def test_stores_transport(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)
        assert protocol._transport is mock_transport

    def test_default_reconnect_settings(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)
        assert protocol._reconnect_attempts == 5
        assert protocol._reconnect_min_wait == 1.0
        assert protocol._reconnect_max_wait == 60.0

    def test_custom_reconnect_settings(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(
            mock_transport,
            reconnect_attempts=3,
            reconnect_min_wait=0.5,
            reconnect_max_wait=30.0,
        )
        assert protocol._reconnect_attempts == 3
        assert protocol._reconnect_min_wait == 0.5
        assert protocol._reconnect_max_wait == 30.0

    def test_not_running_initially(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)
        assert protocol._running is False
        assert protocol.is_connected is False


class TestProtocolStartStop:
    """Tests for Protocol.start() and Protocol.stop()."""

    @pytest.mark.anyio
    async def test_start_sets_running(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)

        # Mock the stream to avoid reading
        mock_stream = AsyncMock()
        mock_stream.receive = AsyncMock(side_effect=anyio.get_cancelled_exc_class())
        mock_transport.stream = mock_stream

        await protocol.start()

        try:
            assert protocol._running is True
            assert protocol.is_connected is True
        finally:
            await protocol.stop()

    @pytest.mark.anyio
    async def test_stop_clears_running(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)

        mock_stream = AsyncMock()
        mock_stream.receive = AsyncMock(side_effect=anyio.get_cancelled_exc_class())
        mock_transport.stream = mock_stream

        await protocol.start()
        await protocol.stop()

        assert protocol._running is False

    @pytest.mark.anyio
    async def test_start_is_idempotent(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)

        mock_stream = AsyncMock()
        mock_stream.receive = AsyncMock(side_effect=anyio.get_cancelled_exc_class())
        mock_transport.stream = mock_stream

        await protocol.start()
        task_group_1 = protocol._task_group

        await protocol.start()  # Second call should be no-op
        task_group_2 = protocol._task_group

        try:
            assert task_group_1 is task_group_2
        finally:
            await protocol.stop()


class TestEventHandlers:
    """Tests for event handler registration and dispatch."""

    def test_on_event_registers_handler(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)

        async def handler(event: ProtoHeartbeatEvent) -> None:
            pass

        protocol.on_event(ProtoHeartbeatEvent, handler)

        assert ProtoHeartbeatEvent in protocol._event_handlers
        assert handler in protocol._event_handlers[ProtoHeartbeatEvent]

    def test_multiple_handlers_for_same_event(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)

        async def handler1(event: ProtoHeartbeatEvent) -> None:
            pass

        async def handler2(event: ProtoHeartbeatEvent) -> None:
            pass

        protocol.on_event(ProtoHeartbeatEvent, handler1)
        protocol.on_event(ProtoHeartbeatEvent, handler2)

        assert len(protocol._event_handlers[ProtoHeartbeatEvent]) == 2

    def test_remove_handler_stops_dispatch(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)

        async def handler(event: ProtoHeartbeatEvent) -> None:
            pass

        protocol.on_event(ProtoHeartbeatEvent, handler)
        protocol.remove_handler(ProtoHeartbeatEvent, handler)

        assert handler not in protocol._event_handlers.get(ProtoHeartbeatEvent, [])

    def test_remove_nonexistent_handler_does_not_raise(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)

        async def handler(event: ProtoHeartbeatEvent) -> None:
            pass

        # Should not raise
        protocol.remove_handler(ProtoHeartbeatEvent, handler)

    @pytest.mark.anyio
    async def test_event_handler_called_for_server_events(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)

        received_events: list[ProtoHeartbeatEvent] = []

        async def handler(event: ProtoHeartbeatEvent) -> None:
            received_events.append(event)

        protocol.on_event(ProtoHeartbeatEvent, handler)

        # Simulate receiving an event
        event = ProtoHeartbeatEvent()
        await protocol._dispatch_event(event)

        assert len(received_events) == 1

    @pytest.mark.anyio
    async def test_handler_exception_does_not_crash_dispatch(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)

        received: list[ProtoHeartbeatEvent] = []

        async def bad_handler(_event: ProtoHeartbeatEvent) -> None:
            raise RuntimeError("Handler error")

        async def good_handler(event: ProtoHeartbeatEvent) -> None:
            received.append(event)

        protocol.on_event(ProtoHeartbeatEvent, bad_handler)
        protocol.on_event(ProtoHeartbeatEvent, good_handler)

        # Should not raise, and good handler should still be called
        event = ProtoHeartbeatEvent()
        await protocol._dispatch_event(event)

        assert len(received) == 1


class TestSendRequest:
    """Tests for Protocol.send_request()."""

    @pytest.mark.anyio
    async def test_send_request_raises_when_not_running(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)

        with pytest.raises(CTraderConnectionClosedError):
            await protocol.send_request(ProtoOAVersionReq())

    @pytest.mark.anyio
    async def test_send_request_timeout_raises(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)
        protocol._running = True

        with pytest.raises(CTraderConnectionTimeoutError) as exc_info:
            await protocol.send_request(ProtoOAVersionReq(), timeout=0.01)

        assert exc_info.value.timeout_seconds == 0.01

    @pytest.mark.anyio
    async def test_send_request_correlates_response(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)
        protocol._running = True

        async def respond() -> None:
            await anyio.sleep(0.01)
            # Simulate response arriving
            msg_id = "1"  # First message ID
            protocol._results[msg_id] = ProtoOAVersionRes(version="1.0")
            protocol._pending[msg_id].set()

        async with anyio.create_task_group() as tg:
            tg.start_soon(respond)
            result = await protocol.send_request(ProtoOAVersionReq(), timeout=1.0)

        assert isinstance(result, ProtoOAVersionRes)

    @pytest.mark.anyio
    async def test_send_request_error_response_raises_api_error(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)
        protocol._running = True

        async def respond_with_error() -> None:
            await anyio.sleep(0.01)
            msg_id = "1"
            error = APIError("TEST_ERROR", "Test error description")
            protocol._errors[msg_id] = error
            protocol._pending[msg_id].set()

        async with anyio.create_task_group() as tg:
            tg.start_soon(respond_with_error)

            with pytest.raises(APIError) as exc_info:
                await protocol.send_request(ProtoOAVersionReq(), timeout=1.0)

        assert exc_info.value.error_code == "TEST_ERROR"


class TestSendEvent:
    """Tests for Protocol.send_event()."""

    @pytest.mark.anyio
    async def test_send_event_raises_when_not_running(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)

        with pytest.raises(CTraderConnectionClosedError):
            await protocol.send_event(ProtoHeartbeatEvent())

    @pytest.mark.anyio
    async def test_send_event_sends_message(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)
        protocol._running = True

        await protocol.send_event(ProtoHeartbeatEvent())

        mock_transport.send.assert_called_once()


class TestMessageDispatch:
    """Tests for message dispatch logic."""

    @pytest.mark.anyio
    async def test_dispatch_routes_response_to_pending_request(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)

        # Set up a pending request
        msg_id = "test-123"
        event = anyio.Event()
        protocol._pending[msg_id] = event

        proto_msg = ProtoMessage(
            payload_type=ProtoPayloadType.HEARTBEAT_EVENT,
            client_msg_id=msg_id,
        )
        inner = ProtoHeartbeatEvent()

        await protocol._dispatch_message(proto_msg, inner)

        assert event.is_set()
        assert msg_id in protocol._results

    @pytest.mark.anyio
    async def test_dispatch_routes_error_response_to_errors(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)

        msg_id = "test-123"
        event = anyio.Event()
        protocol._pending[msg_id] = event

        proto_msg = ProtoMessage(
            payload_type=ProtoPayloadType.ERROR_RES,
            client_msg_id=msg_id,
        )
        inner = ProtoOAErrorRes(error_code="TEST_ERROR")

        await protocol._dispatch_message(proto_msg, inner)

        assert event.is_set()
        assert msg_id in protocol._errors
        assert isinstance(protocol._errors[msg_id], APIError)

    @pytest.mark.anyio
    async def test_dispatch_routes_event_to_handlers(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport)

        received: list[ProtoHeartbeatEvent] = []

        async def handler(event: ProtoHeartbeatEvent) -> None:
            received.append(event)

        protocol.on_event(ProtoHeartbeatEvent, handler)

        proto_msg = ProtoMessage(
            payload_type=ProtoPayloadType.HEARTBEAT_EVENT,
            client_msg_id="",  # No msg_id = server event
        )
        inner = ProtoHeartbeatEvent()

        await protocol._dispatch_message(proto_msg, inner)

        assert len(received) == 1


class TestReconnect:
    """Tests for reconnection logic."""

    @pytest.mark.anyio
    async def test_reconnect_disabled_raises_immediately(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport, reconnect_attempts=0)

        with pytest.raises(CTraderConnectionClosedError) as exc_info:
            await protocol._reconnect()

        assert "reconnection disabled" in str(exc_info.value)

    @pytest.mark.anyio
    async def test_reconnect_calls_transport_connect(self, mock_transport: MagicMock) -> None:
        protocol = Protocol(mock_transport, reconnect_attempts=1)

        await protocol._reconnect()

        mock_transport.connect.assert_called_once()

    @pytest.mark.anyio
    async def test_reconnect_with_tenacity_backoff(self, mock_transport: MagicMock) -> None:
        from ctrader_api_client.exceptions import CTraderConnectionFailedError

        protocol = Protocol(
            mock_transport,
            reconnect_attempts=3,
            reconnect_min_wait=0.01,
            reconnect_max_wait=0.02,
        )

        # Fail twice, succeed on third
        call_count = 0

        async def connect_with_failures() -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise CTraderConnectionFailedError("host", 5035, None)

        mock_transport.connect = AsyncMock(side_effect=connect_with_failures)

        await protocol._reconnect()

        assert call_count == 3
