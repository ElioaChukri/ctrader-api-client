"""Tests for the Transport class."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ctrader_api_client.connection.transport import Transport
from ctrader_api_client.exceptions import (
    CTraderConnectionClosedError,
    CTraderConnectionFailedError,
)


class TestTransportInit:
    """Tests for Transport initialization."""

    def test_stores_host_and_port(self) -> None:
        transport = Transport("example.com", 5035)
        assert transport.host == "example.com"
        assert transport.port == 5035

    def test_ssl_enabled_by_default(self) -> None:
        transport = Transport("example.com", 5035)
        assert transport._ssl is True

    def test_ssl_can_be_disabled(self) -> None:
        transport = Transport("example.com", 5035, use_ssl=False)
        assert transport._ssl is False

    def test_not_connected_initially(self) -> None:
        transport = Transport("example.com", 5035)
        assert transport.is_connected is False


class TestTransportConnect:
    """Tests for Transport.connect()."""

    @pytest.mark.anyio
    async def test_connect_establishes_connection(self) -> None:
        transport = Transport("example.com", 5035)
        mock_stream = MagicMock()

        with patch("anyio.connect_tcp", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_stream
            await transport.connect()

        assert transport.is_connected is True
        mock_connect.assert_called_once()

    @pytest.mark.anyio
    async def test_connect_uses_ssl_by_default(self) -> None:
        transport = Transport("example.com", 5035)
        mock_stream = MagicMock()

        with (
            patch("anyio.connect_tcp", new_callable=AsyncMock) as mock_connect,
            patch("ssl.create_default_context") as mock_ssl_context,
        ):
            mock_connect.return_value = mock_stream
            await transport.connect()

        mock_ssl_context.assert_called_once()
        call_kwargs = mock_connect.call_args.kwargs
        assert "ssl_context" in call_kwargs
        assert call_kwargs["tls_standard_compatible"] is True

    @pytest.mark.anyio
    async def test_connect_without_ssl(self) -> None:
        transport = Transport("example.com", 5035, use_ssl=False)
        mock_stream = MagicMock()

        with patch("anyio.connect_tcp", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_stream
            await transport.connect()

        call_kwargs = mock_connect.call_args.kwargs
        assert "ssl_context" not in call_kwargs

    @pytest.mark.anyio
    async def test_connect_raises_connection_failed_error_on_os_error(self) -> None:
        transport = Transport("example.com", 5035)

        with patch("anyio.connect_tcp", new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = OSError("Connection refused")

            with pytest.raises(CTraderConnectionFailedError) as exc_info:
                await transport.connect()

        assert exc_info.value.host == "example.com"
        assert exc_info.value.port == 5035

    @pytest.mark.anyio
    async def test_connect_is_idempotent(self) -> None:
        transport = Transport("example.com", 5035)
        mock_stream = MagicMock()

        with patch("anyio.connect_tcp", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_stream
            await transport.connect()
            await transport.connect()  # Second call should be no-op

        mock_connect.assert_called_once()


class TestTransportClose:
    """Tests for Transport.close()."""

    @pytest.mark.anyio
    async def test_close_disconnects(self) -> None:
        transport = Transport("example.com", 5035)
        mock_stream = AsyncMock()

        with patch("anyio.connect_tcp", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_stream
            await transport.connect()

        await transport.close()

        assert transport.is_connected is False
        mock_stream.aclose.assert_called_once()

    @pytest.mark.anyio
    async def test_close_is_idempotent(self) -> None:
        transport = Transport("example.com", 5035)
        mock_stream = AsyncMock()

        with patch("anyio.connect_tcp", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_stream
            await transport.connect()

        await transport.close()
        await transport.close()  # Second call should be no-op

        mock_stream.aclose.assert_called_once()

    @pytest.mark.anyio
    async def test_close_when_not_connected(self) -> None:
        transport = Transport("example.com", 5035)
        await transport.close()  # Should not raise
        assert transport.is_connected is False


class TestTransportSend:
    """Tests for Transport.send()."""

    @pytest.mark.anyio
    async def test_send_transmits_data(self) -> None:
        transport = Transport("example.com", 5035)
        mock_stream = AsyncMock()

        with patch("anyio.connect_tcp", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_stream
            await transport.connect()

        await transport.send(b"test data")

        mock_stream.send.assert_called_once_with(b"test data")

    @pytest.mark.anyio
    async def test_send_raises_when_not_connected(self) -> None:
        transport = Transport("example.com", 5035)

        with pytest.raises(CTraderConnectionClosedError):
            await transport.send(b"test data")


class TestTransportReceive:
    """Tests for Transport.receive()."""

    @pytest.mark.anyio
    async def test_receive_returns_data(self) -> None:
        transport = Transport("example.com", 5035)
        mock_stream = AsyncMock()
        mock_stream.receive.return_value = b"response data"

        with patch("anyio.connect_tcp", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_stream
            await transport.connect()

        data = await transport.receive(1024)

        assert data == b"response data"
        mock_stream.receive.assert_called_once_with(1024)

    @pytest.mark.anyio
    async def test_receive_raises_when_not_connected(self) -> None:
        transport = Transport("example.com", 5035)

        with pytest.raises(CTraderConnectionClosedError):
            await transport.receive(1024)


class TestTransportStream:
    """Tests for Transport.stream property."""

    @pytest.mark.anyio
    async def test_stream_returns_underlying_stream(self) -> None:
        transport = Transport("example.com", 5035)
        mock_stream = AsyncMock()

        with patch("anyio.connect_tcp", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_stream
            await transport.connect()

        assert transport.stream is mock_stream

    def test_stream_raises_when_not_connected(self) -> None:
        transport = Transport("example.com", 5035)

        with pytest.raises(CTraderConnectionClosedError):
            _ = transport.stream


class TestIsConnected:
    """Tests for Transport.is_connected property."""

    def test_is_connected_false_initially(self) -> None:
        transport = Transport("example.com", 5035)
        assert transport.is_connected is False

    @pytest.mark.anyio
    async def test_is_connected_true_after_connect(self) -> None:
        transport = Transport("example.com", 5035)
        mock_stream = MagicMock()

        with patch("anyio.connect_tcp", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_stream
            await transport.connect()

        assert transport.is_connected is True

    @pytest.mark.anyio
    async def test_is_connected_false_after_close(self) -> None:
        transport = Transport("example.com", 5035)
        mock_stream = AsyncMock()

        with patch("anyio.connect_tcp", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_stream
            await transport.connect()

        await transport.close()
        assert transport.is_connected is False
