"""Unit tests for serialization module."""

from __future__ import annotations

import struct
from unittest.mock import AsyncMock

import pytest

from ctrader_api_client._internal.proto import ProtoHeartbeatEvent, ProtoOAApplicationAuthReq
from ctrader_api_client._internal.serialization import (
    _LENGTH_PREFIX_FORMAT,
    _MAX_MESSAGE_SIZE,
    encode_with_length_prefix,
    read_exact,
    read_framed_message,
)
from ctrader_api_client.exceptions import FramingError


class TestEncodeWithLengthPrefix:
    """Tests for encode_with_length_prefix function."""

    def test_produces_correct_length_prefix(self) -> None:
        """Length prefix should be 4-byte big-endian unsigned int."""
        message = ProtoHeartbeatEvent()
        encoded = encode_with_length_prefix(message)

        # First 4 bytes are the length prefix
        length_prefix = encoded[:4]
        payload = encoded[4:]

        # Decode the length prefix
        (length,) = struct.unpack(_LENGTH_PREFIX_FORMAT, length_prefix)

        assert length == len(payload)

    def test_payload_follows_prefix(self) -> None:
        """Payload should immediately follow the 4-byte prefix."""
        message = ProtoHeartbeatEvent()
        serialized_message = bytes(message)
        encoded = encode_with_length_prefix(message)

        assert encoded[4:] == serialized_message

    def test_total_length_is_prefix_plus_payload(self) -> None:
        """Total encoded length should be 4 + payload length."""
        message = ProtoOAApplicationAuthReq(client_id="test", client_secret="secret")
        serialized_message = bytes(message)
        encoded = encode_with_length_prefix(message)

        assert len(encoded) == 4 + len(serialized_message)

    def test_empty_message(self) -> None:
        """Empty message should have length prefix of 0 or minimal size."""
        message = ProtoHeartbeatEvent()
        encoded = encode_with_length_prefix(message)

        (length,) = struct.unpack(_LENGTH_PREFIX_FORMAT, encoded[:4])
        # HeartbeatEvent has a payload_type field, so it's not completely empty
        assert length >= 0


class TestReadExact:
    """Tests for read_exact function."""

    @pytest.mark.anyio
    async def test_returns_exact_bytes(self) -> None:
        """Should return exactly the requested number of bytes."""
        mock_stream = AsyncMock()
        mock_stream.receive.return_value = b"hello"

        result = await read_exact(mock_stream, 5)

        assert result == b"hello"
        mock_stream.receive.assert_called_once_with(5)

    @pytest.mark.anyio
    async def test_handles_fragmented_reads(self) -> None:
        """Should handle data arriving in multiple chunks."""
        mock_stream = AsyncMock()
        mock_stream.receive.side_effect = [b"hel", b"lo"]

        result = await read_exact(mock_stream, 5)

        assert result == b"hello"
        assert mock_stream.receive.call_count == 2

    @pytest.mark.anyio
    async def test_raises_framing_error_on_early_close(self) -> None:
        """Should raise FramingError if stream closes before enough bytes."""
        mock_stream = AsyncMock()
        mock_stream.receive.side_effect = [b"hel", b""]  # Stream closes after 3 bytes

        with pytest.raises(FramingError) as exc_info:
            await read_exact(mock_stream, 5)

        assert exc_info.value.expected_bytes == 5
        assert exc_info.value.received_bytes == 3

    @pytest.mark.anyio
    async def test_raises_framing_error_on_immediate_close(self) -> None:
        """Should raise FramingError if stream is immediately empty."""
        mock_stream = AsyncMock()
        mock_stream.receive.return_value = b""

        with pytest.raises(FramingError) as exc_info:
            await read_exact(mock_stream, 5)

        assert exc_info.value.expected_bytes == 5
        assert exc_info.value.received_bytes == 0


class TestReadFramedMessage:
    """Tests for read_framed_message function."""

    @pytest.mark.anyio
    async def test_reads_length_and_payload(self) -> None:
        """Should correctly read length prefix then payload."""
        payload = b"test payload"
        length_prefix = struct.pack(_LENGTH_PREFIX_FORMAT, len(payload))

        mock_stream = AsyncMock()
        # First call returns length prefix, second returns payload
        mock_stream.receive.side_effect = [length_prefix, payload]

        result = await read_framed_message(mock_stream)

        assert result == payload

    @pytest.mark.anyio
    async def test_raises_framing_error_on_oversized_message(self) -> None:
        """Should raise FramingError if message size exceeds maximum."""
        oversized_length = _MAX_MESSAGE_SIZE + 1
        length_prefix = struct.pack(_LENGTH_PREFIX_FORMAT, oversized_length)

        mock_stream = AsyncMock()
        mock_stream.receive.return_value = length_prefix

        with pytest.raises(FramingError) as exc_info:
            await read_framed_message(mock_stream)

        assert exc_info.value.expected_bytes == _MAX_MESSAGE_SIZE
        assert exc_info.value.received_bytes == oversized_length

    @pytest.mark.anyio
    async def test_raises_framing_error_on_truncated_length(self) -> None:
        """Should raise FramingError if stream closes during length prefix."""
        mock_stream = AsyncMock()
        mock_stream.receive.side_effect = [b"\x00\x00", b""]  # Only 2 bytes of length

        with pytest.raises(FramingError) as exc_info:
            await read_framed_message(mock_stream)

        assert exc_info.value.expected_bytes == 4
        assert exc_info.value.received_bytes == 2

    @pytest.mark.anyio
    async def test_raises_framing_error_on_truncated_payload(self) -> None:
        """Should raise FramingError if stream closes during payload."""
        payload_length = 100
        length_prefix = struct.pack(_LENGTH_PREFIX_FORMAT, payload_length)
        partial_payload = b"x" * 50

        mock_stream = AsyncMock()
        mock_stream.receive.side_effect = [length_prefix, partial_payload, b""]

        with pytest.raises(FramingError) as exc_info:
            await read_framed_message(mock_stream)

        assert exc_info.value.expected_bytes == payload_length
        assert exc_info.value.received_bytes == 50
