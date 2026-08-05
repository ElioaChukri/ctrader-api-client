from __future__ import annotations

import logging
from collections.abc import Callable

import anyio
import anyio.abc
import betterproto

from .._internal import Clock, MonotonicClock
from .._internal.proto import ProtoHeartbeatEvent
from .protocol import Protocol


logger = logging.getLogger(__name__)


class HeartbeatManager:
    """Manages heartbeat send/receive for keep-alive.

    Sends periodic heartbeats to the server and monitors for incoming
    heartbeats to detect connection loss.
    """

    def __init__(
        self,
        protocol: Protocol,
        interval: float = 10.0,
        timeout: float = 30.0,
        clock: Clock | None = None,
    ) -> None:
        """Initialize the heartbeat manager.

        Args:
            protocol: The protocol instance to send/receive through.
            interval: Seconds between heartbeat sends.
            timeout: Seconds without server heartbeat before triggering disconnect.
            clock: Time source for the send interval and inactivity timer.
        """
        self._protocol = protocol
        self._interval = interval
        self._timeout = timeout
        self._clock = clock if clock is not None else MonotonicClock()
        self._last_received: float = 0.0
        self._task_scope: anyio.CancelScope | None = None
        self._task_group: anyio.abc.TaskGroup | None = None
        self._disposers: list[Callable[[], None]] = []

    async def serve(self, *, task_status: anyio.abc.TaskStatus[None] = anyio.TASK_STATUS_IGNORED) -> None:
        """Run the heartbeat send loop until stopped or cancelled.

        Handler registration is undone as this returns, so a monitor that is no
        longer running cannot keep resetting the inactivity timer.

        Raises:
            RuntimeError: If the monitor is already being served.
        """
        if self._disposers:
            raise RuntimeError("Heartbeat monitor is already running")

        self._disposers = [
            # Track activity on any server message, not just heartbeats
            self._protocol.on_event(betterproto.Message, self._record_activity),
            # Keep heartbeat handler for debug logging
            self._protocol.on_event(ProtoHeartbeatEvent, self._on_heartbeat),
        ]
        self._last_received = self._clock.now()

        logger.debug("Heartbeat monitor started (interval=%.1fs, timeout=%.1fs)", self._interval, self._timeout)
        try:
            async with anyio.create_task_group() as task_group:
                self._task_group = task_group
                task_group.start_soon(self._heartbeat_loop)
                task_status.started()
        finally:
            self._task_group = None
            self._task_scope = None
            for dispose in self._disposers:
                dispose()
            self._disposers.clear()
            logger.debug("Heartbeat monitor stopped")

    async def stop(self) -> None:
        """Ask the heartbeat loop to wind down."""
        if self._task_scope is not None:
            self._task_scope.cancel()

        if self._task_group is not None:
            self._task_group.cancel_scope.cancel()

    async def restart(self) -> None:
        """Restart heartbeat monitoring after reconnection.

        Resets the heartbeat timer and spawns a new heartbeat loop.
        Should be called after the protocol has reconnected.
        """
        # Cancel any heartbeat loop still running from the previous connection.
        # When a drop is detected by the reader loop (not by a heartbeat
        # timeout/send failure), the old loop is merely asleep and would
        # otherwise survive the reconnect, leaving two loops running and
        # accumulating one extra on every reconnect.
        if self._task_scope is not None:
            self._task_scope.cancel()

        self._last_received = self._clock.now()
        if self._task_group is not None:
            self._task_group.start_soon(self._heartbeat_loop)
        logger.debug("Heartbeat monitor restarted")

    async def _record_activity(self, _message: betterproto.Message) -> None:
        """Reset the inactivity timer on any received server message."""
        self._last_received = self._clock.now()

    async def _on_heartbeat(self, _event: ProtoHeartbeatEvent) -> None:
        """Handler called when an explicit heartbeat is received from the server."""
        logger.debug("Heartbeat received from server")

    async def _heartbeat_loop(self) -> None:
        """Periodically send heartbeats and check for timeout."""
        with anyio.CancelScope() as scope:
            self._task_scope = scope
            while True:
                await self._clock.sleep(self._interval)

                # Check if server heartbeat received recently
                elapsed = self._clock.now() - self._last_received
                if 0 < self._timeout < elapsed:
                    logger.warning(
                        "Heartbeat timeout: no heartbeat received in %.1f seconds",
                        elapsed,
                    )
                    # Heartbeat timeout - trigger disconnect handling
                    await self._protocol.handle_disconnect()
                    return

                # Send client heartbeat
                try:
                    await self._protocol.send_event(ProtoHeartbeatEvent())
                    logger.debug("Heartbeat sent to server")
                except Exception as e:
                    logger.warning("Failed to send heartbeat: %s", e)
                    # A failed write can be the first (or only) sign of a
                    # half-open connection, so drive reconnection explicitly
                    # instead of relying on the reader loop to notice.
                    await self._protocol.handle_disconnect()
                    return
