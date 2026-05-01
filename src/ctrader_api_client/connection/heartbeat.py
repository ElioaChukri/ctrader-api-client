from __future__ import annotations

import logging
import time

import anyio
import anyio.abc
import betterproto

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
    ) -> None:
        """Initialize the heartbeat manager.

        Args:
            protocol: The protocol instance to send/receive through.
            interval: Seconds between heartbeat sends.
            timeout: Seconds without server heartbeat before triggering disconnect.
        """
        self._protocol = protocol
        self._interval = interval
        self._timeout = timeout
        self._last_received: float = 0.0
        self._task_scope: anyio.CancelScope | None = None
        self._task_group: anyio.abc.TaskGroup | None = None

    async def start(self) -> None:
        """Start heartbeat monitoring.

        Registers event handlers and starts the heartbeat send loop.
        """
        # Track activity on any server message, not just heartbeats
        self._protocol.on_event(betterproto.Message, self._record_activity)
        # Keep heartbeat handler for debug logging
        self._protocol.on_event(ProtoHeartbeatEvent, self._on_heartbeat)
        self._last_received = time.monotonic()

        # Start heartbeat loop in background
        self._task_group = anyio.create_task_group()
        await self._task_group.__aenter__()
        self._task_group.start_soon(self._heartbeat_loop)
        logger.info("Heartbeat monitor started (interval=%.1fs, timeout=%.1fs)", self._interval, self._timeout)

    async def stop(self) -> None:
        """Stop heartbeat monitoring.

        Cancels the heartbeat loop and removes event handlers.
        """
        if self._task_scope is not None:
            self._task_scope.cancel()

        if self._task_group is not None:
            logger.info("Heartbeat monitor stopped")
            self._task_group.cancel_scope.cancel()
            try:
                await self._task_group.__aexit__(None, None, None)
            except Exception:
                pass
            self._task_group = None

        self._protocol.remove_handler(betterproto.Message, self._record_activity)
        self._protocol.remove_handler(ProtoHeartbeatEvent, self._on_heartbeat)

    async def restart(self) -> None:
        """Restart heartbeat monitoring after reconnection.

        Resets the heartbeat timer and spawns a new heartbeat loop.
        Should be called after the protocol has reconnected.
        """
        self._last_received = time.monotonic()
        if self._task_group is not None:
            self._task_group.start_soon(self._heartbeat_loop)
        logger.info("Heartbeat monitor restarted")

    async def _record_activity(self, _message: betterproto.Message) -> None:
        """Reset the inactivity timer on any received server message."""
        self._last_received = time.monotonic()

    async def _on_heartbeat(self, _event: ProtoHeartbeatEvent) -> None:
        """Handler called when an explicit heartbeat is received from the server."""
        logger.debug("Heartbeat received from server")

    async def _heartbeat_loop(self) -> None:
        """Periodically send heartbeats and check for timeout."""
        with anyio.CancelScope() as scope:
            self._task_scope = scope
            while True:
                await anyio.sleep(self._interval)

                # Check if server heartbeat received recently
                elapsed = time.monotonic() - self._last_received
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
                    # Protocol will handle reconnection
                    return
