"""Tests for the HeartbeatManager class."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import anyio
import pytest

from ctrader_api_client._internal.proto import ProtoHeartbeatEvent
from ctrader_api_client.connection.heartbeat import HeartbeatManager
from ctrader_api_client.connection.protocol import Protocol


@pytest.fixture
def mock_protocol() -> MagicMock:
    """Create a mock protocol."""
    protocol = MagicMock(spec=Protocol)
    protocol.on_event = MagicMock()
    protocol.remove_handler = MagicMock()
    protocol.send_event = AsyncMock()
    protocol._handle_disconnect = AsyncMock()
    return protocol


class TestHeartbeatInit:
    """Tests for HeartbeatManager initialization."""

    def test_stores_protocol(self, mock_protocol: MagicMock) -> None:
        heartbeat = HeartbeatManager(mock_protocol)
        assert heartbeat._protocol is mock_protocol

    def test_default_interval(self, mock_protocol: MagicMock) -> None:
        heartbeat = HeartbeatManager(mock_protocol)
        assert heartbeat._interval == 10.0

    def test_default_timeout(self, mock_protocol: MagicMock) -> None:
        heartbeat = HeartbeatManager(mock_protocol)
        assert heartbeat._timeout == 30.0

    def test_custom_interval_and_timeout(self, mock_protocol: MagicMock) -> None:
        heartbeat = HeartbeatManager(mock_protocol, interval=5.0, timeout=15.0)
        assert heartbeat._interval == 5.0
        assert heartbeat._timeout == 15.0


class TestHeartbeatStart:
    """Tests for HeartbeatManager.start()."""

    @pytest.mark.anyio
    async def test_start_registers_handler(self, mock_protocol: MagicMock) -> None:
        heartbeat = HeartbeatManager(mock_protocol, interval=0.01, timeout=1.0)

        await heartbeat.start()

        try:
            # Check that on_event was called with ProtoHeartbeatEvent
            mock_protocol.on_event.assert_called_once()
            call_args = mock_protocol.on_event.call_args
            assert call_args[0][0] is ProtoHeartbeatEvent
        finally:
            await heartbeat.stop()

    @pytest.mark.anyio
    async def test_start_initializes_last_received(self, mock_protocol: MagicMock) -> None:
        heartbeat = HeartbeatManager(mock_protocol, interval=0.01, timeout=1.0)

        before = time.monotonic()
        await heartbeat.start()
        after = time.monotonic()

        try:
            assert before <= heartbeat._last_received <= after
        finally:
            await heartbeat.stop()


class TestHeartbeatStop:
    """Tests for HeartbeatManager.stop()."""

    @pytest.mark.anyio
    async def test_stop_removes_handler(self, mock_protocol: MagicMock) -> None:
        heartbeat = HeartbeatManager(mock_protocol, interval=0.01, timeout=1.0)

        await heartbeat.start()
        await heartbeat.stop()

        mock_protocol.remove_handler.assert_called_once()
        call_args = mock_protocol.remove_handler.call_args
        assert call_args[0][0] is ProtoHeartbeatEvent

    @pytest.mark.anyio
    async def test_stop_cancels_loop(self, mock_protocol: MagicMock) -> None:
        heartbeat = HeartbeatManager(mock_protocol, interval=0.01, timeout=1.0)

        await heartbeat.start()
        assert heartbeat._task_group is not None

        await heartbeat.stop()
        assert heartbeat._task_group is None


class TestHeartbeatReceived:
    """Tests for heartbeat event handling."""

    @pytest.mark.anyio
    async def test_heartbeat_updates_last_received(self, mock_protocol: MagicMock) -> None:
        heartbeat = HeartbeatManager(mock_protocol)

        initial_time = time.monotonic() - 100  # Set to past
        heartbeat._last_received = initial_time

        await heartbeat._on_heartbeat(ProtoHeartbeatEvent())

        assert heartbeat._last_received > initial_time


class TestHeartbeatSend:
    """Tests for heartbeat sending."""

    @pytest.mark.anyio
    async def test_heartbeat_sends_periodically(self, mock_protocol: MagicMock) -> None:
        heartbeat = HeartbeatManager(mock_protocol, interval=0.02, timeout=1.0)

        await heartbeat.start()

        try:
            # Wait for at least one heartbeat to be sent
            await anyio.sleep(0.05)
        finally:
            await heartbeat.stop()

        # Check that send_event was called with ProtoHeartbeatEvent
        assert mock_protocol.send_event.call_count >= 1
        for call in mock_protocol.send_event.call_args_list:
            assert isinstance(call[0][0], ProtoHeartbeatEvent)


class TestHeartbeatTimeout:
    """Tests for heartbeat timeout handling."""

    @pytest.mark.anyio
    async def test_heartbeat_timeout_triggers_disconnect(self, mock_protocol: MagicMock) -> None:
        # Very short timeout to trigger quickly
        heartbeat = HeartbeatManager(mock_protocol, interval=0.01, timeout=0.02)

        # Set last_received to past to trigger timeout
        heartbeat._last_received = time.monotonic() - 1.0

        await heartbeat.start()

        # Wait for timeout check to occur
        await anyio.sleep(0.05)

        # The heartbeat loop should have triggered disconnect
        mock_protocol.handle_disconnect.assert_called()

    @pytest.mark.anyio
    async def test_no_timeout_when_heartbeats_received(self, mock_protocol: MagicMock) -> None:
        heartbeat = HeartbeatManager(mock_protocol, interval=0.02, timeout=0.1)

        await heartbeat.start()

        try:
            # Simulate receiving heartbeats
            for _ in range(3):
                await anyio.sleep(0.03)
                await heartbeat._on_heartbeat(ProtoHeartbeatEvent())
        finally:
            await heartbeat.stop()

        # Disconnect should not have been triggered
        mock_protocol._handle_disconnect.assert_not_called()


class TestHeartbeatSendFailure:
    """Tests for handling send failures."""

    @pytest.mark.anyio
    async def test_send_failure_exits_loop(self, mock_protocol: MagicMock) -> None:
        heartbeat = HeartbeatManager(mock_protocol, interval=0.01, timeout=1.0)

        # Make send_event fail
        mock_protocol.send_event = AsyncMock(side_effect=RuntimeError("Send failed"))

        await heartbeat.start()

        # Wait for the loop to encounter the error and exit
        await anyio.sleep(0.05)

        # The task should have exited (stop should complete cleanly)
        await heartbeat.stop()
