from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio

from .heartbeat import HeartbeatManager
from .listener import ConnectionListener
from .protocol import Protocol
from .transport import Transport


logger = logging.getLogger(__name__)


class ConnectionSupervisor:
    """Owns the link and everything whose life is bounded by it.

    Brings up the transport, the protocol reader and the heartbeat in the one
    order that works, holds them for the length of a `serving()` block, and
    reports every link transition to its listeners. Whoever runs a supervisor
    therefore never has to know that ordering, nor that a reconnection needs the
    heartbeat put back before anything else can be restored.
    """

    def __init__(
        self,
        transport: Transport,
        protocol: Protocol,
        heartbeat: HeartbeatManager,
    ) -> None:
        """Take ownership of the connection layer.

        Args:
            transport: The TCP/SSL link.
            protocol: Framing and correlation over that link. The supervisor
                registers itself as its listener, so drops detected by the
                reader arrive here.
            heartbeat: Keeps the link alive and notices when it goes quiet.
        """
        self._transport = transport
        self._protocol = protocol
        self._heartbeat = heartbeat
        self._listeners: list[ConnectionListener] = []
        self._serving = False

        protocol.set_listener(self)

    def add_listener(self, listener: ConnectionListener) -> None:
        """Register a party to be told when the link drops and comes back.

        Args:
            listener: Told after the supervisor has restored its own machinery,
                so a listener is free to send on the new link.
        """
        self._listeners.append(listener)

    @property
    def is_connected(self) -> bool:
        """Whether the supervisor is serving a live link."""
        return self._serving and self._transport.is_connected

    @asynccontextmanager
    async def serving(self) -> AsyncIterator[None]:
        """Hold the connection and the loops that run on it open for the block.

        Connecting happens before the block is entered, so a failure to reach
        the server is raised as itself rather than as whatever a task group
        would make of it. The loops are wound down and the transport closed on
        the way out, however the block ends.

        Raises:
            CTraderConnectionFailedError: If the connection cannot be established.
        """
        logger.debug("Connecting to %s:%d", self._transport.host, self._transport.port)
        await self._transport.connect()
        try:
            async with anyio.create_task_group() as task_group:
                await task_group.start(self._protocol.serve)
                await task_group.start(self._heartbeat.serve)

                self._serving = True
                logger.info("Connected to cTrader server at %s:%d", self._transport.host, self._transport.port)
                try:
                    yield
                finally:
                    # The heartbeat goes first so nothing tries to write to a
                    # protocol that is already winding down.
                    self._serving = False
                    await self._heartbeat.stop()
                    await self._protocol.stop()
        finally:
            await self._transport.close()
            logger.debug("Connection closed")

    async def on_connection_lost(self) -> None:
        """Report a dropped link onward so link-scoped state can be discarded.

        A listener that fails is logged and skipped: reconnection is more
        important than any one listener's bookkeeping, and the listeners after
        it still need to hear about the drop.
        """
        for listener in self._listeners:
            try:
                await listener.on_connection_lost()
            except Exception:
                logger.exception("Connection listener failed while handling a disconnect")

    async def on_connection_restored(self) -> None:
        """Put the link-scoped machinery back, then report the recovery onward.

        The heartbeat is restarted first because the loop that was watching the
        dead link is either gone or asleep on a timer that no longer means
        anything; listeners are told once the link is fully serviced again.
        """
        await self._heartbeat.restart()

        for listener in self._listeners:
            try:
                await listener.on_connection_restored()
            except Exception:
                logger.exception("Connection listener failed while handling a reconnect")
