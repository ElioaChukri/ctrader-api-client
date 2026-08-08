from __future__ import annotations

import logging
import ssl

import anyio
from anyio.abc import ByteReceiveStream, ByteStream

from ..exceptions import CTraderConnectionClosedError, CTraderConnectionFailedError


logger = logging.getLogger(__name__)


class Transport:
    """Low-level TCP/SSL transport.

    Handles raw socket connections without knowledge of protobuf or message semantics.
    """

    def __init__(self, host: str, port: int, use_ssl: bool = True, connect_timeout: float = 30.0) -> None:
        """Initialize transport configuration.

        Args:
            host: The server hostname to connect to.
            port: The server port to connect to.
            use_ssl: Whether to use SSL/TLS encryption. Defaults to True.
            connect_timeout: Seconds to allow for the TCP connection and the
                TLS handshake together. Bounds the one failure mode a caller
                cannot retry: a handshake that neither completes nor fails.
        """
        self._host = host
        self._port = port
        self._ssl = use_ssl
        self._connect_timeout = connect_timeout
        self._stream: ByteStream | None = None

    @property
    def host(self) -> str:
        """The host this transport connects to."""
        return self._host

    @property
    def port(self) -> int:
        """The port this transport connects to."""
        return self._port

    @property
    def is_connected(self) -> bool:
        """Whether transport has an active connection."""
        return self._stream is not None

    @property
    def stream(self) -> ByteReceiveStream:
        """Get the underlying stream for reading.

        Raises:
            CTraderConnectionClosedError: If not connected.
        """
        if self._stream is None:
            raise CTraderConnectionClosedError("Not connected")
        return self._stream

    async def connect(self) -> None:
        """Establish TCP/SSL connection.

        If already connected, this method returns immediately.

        Either returns with a usable stream or raises
        `CTraderConnectionFailedError`. There is deliberately no third outcome:
        anything that goes wrong on the way to a connection *is* a failure to
        connect, whatever its type, so callers can retry on one exception
        rather than on a list of them that has to be kept complete.

        Raises:
            CTraderConnectionFailedError: If connection cannot be established.
        """
        if self._stream is not None:
            return  # Already connected

        try:
            # Every failure is translated, not an enumerated set of them. A TLS
            # handshake cut short by the peer surfaces as anyio's
            # BrokenResourceError, which is not an OSError and so used to
            # escape untranslated — past the retry loop that only knew
            # CTraderConnectionFailedError, and into the handler that reads an
            # unrecognised exception as fatal. Cancellation still passes
            # through: anyio raises it from BaseException, not Exception.
            with anyio.fail_after(self._connect_timeout):
                if self._ssl:
                    ssl_context = ssl.create_default_context()
                    self._stream = await anyio.connect_tcp(
                        self._host,
                        self._port,
                        ssl_context=ssl_context,
                        tls_standard_compatible=True,
                    )
                else:
                    self._stream = await anyio.connect_tcp(self._host, self._port)
        except Exception as e:
            raise CTraderConnectionFailedError(self._host, self._port, e) from e

        if self._ssl:
            logger.debug("Connected to %s:%d with SSL", self._host, self._port)
        else:
            logger.warning("Connected to %s:%d without SSL (plaintext)", self._host, self._port)

    async def close(self) -> None:
        """Close the connection gracefully.

        This method is idempotent - calling it multiple times is safe.
        Handles already-closed streams gracefully.
        """
        if self._stream is not None:
            stream = self._stream
            self._stream = None  # Clear reference first to prevent re-entry
            try:
                # move_on_after guards against aclose() hanging when the network
                # route has changed (e.g. VPN toggle) but the OS hasn't reset the
                # TCP socket — graceful TLS shutdown would wait forever for an ACK.
                with anyio.move_on_after(5) as close_scope:
                    await stream.aclose()
                if close_scope.cancelled_caught:
                    logger.debug("Graceful TLS shutdown timed out, forcing close")
            except (OSError, anyio.ClosedResourceError, anyio.BrokenResourceError):
                pass

    async def send(self, data: bytes) -> None:
        """Send raw bytes over the connection.

        Args:
            data: The bytes to send.

        Raises:
            CTraderConnectionClosedError: If not connected.
        """
        if self._stream is None:
            raise CTraderConnectionClosedError("Not connected")
        await self._stream.send(data)

    async def receive(self, max_bytes: int) -> bytes:
        """Receive up to max_bytes from the connection.

        Args:
            max_bytes: Maximum number of bytes to receive.

        Returns:
            The received bytes, or empty bytes on EOF.

        Raises:
            CTraderConnectionClosedError: If not connected.
        """
        if self._stream is None:
            raise CTraderConnectionClosedError("Not connected")
        return await self._stream.receive(max_bytes)
