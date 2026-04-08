from __future__ import annotations

import ssl

import anyio
from anyio.abc import ByteReceiveStream, ByteStream

from ..exceptions import CTraderConnectionClosedError, CTraderConnectionFailedError


class Transport:
    """Low-level TCP/SSL transport.

    Handles raw socket connections without knowledge of protobuf or message semantics.
    """

    def __init__(self, host: str, port: int, use_ssl: bool = True) -> None:
        """Initialize transport configuration.

        Args:
            host: The server hostname to connect to.
            port: The server port to connect to.
            use_ssl: Whether to use SSL/TLS encryption. Defaults to True.
        """
        self._host = host
        self._port = port
        self._ssl = use_ssl
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

        Raises:
            CTraderConnectionFailedError: If connection cannot be established.
        """
        if self._stream is not None:
            return  # Already connected

        try:
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
        except OSError as e:
            raise CTraderConnectionFailedError(self._host, self._port, e) from e

    async def close(self) -> None:
        """Close the connection gracefully.

        This method is idempotent - calling it multiple times is safe.
        """
        if self._stream is not None:
            await self._stream.aclose()
            self._stream = None

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
