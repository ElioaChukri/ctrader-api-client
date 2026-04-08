from __future__ import annotations

import struct

import betterproto
from anyio.abc import ByteReceiveStream

from ..exceptions import FramingError


# Big-endian unsigned 4-byte integer format
_LENGTH_PREFIX_FORMAT = ">I"
_LENGTH_PREFIX_SIZE = 4

# Safety limit to prevent memory exhaustion from malformed messages
_MAX_MESSAGE_SIZE = 1024 * 1024  # 1MB


def encode_with_length_prefix(message: betterproto.Message) -> bytes:
    """Encode a protobuf message with 4-byte big-endian length prefix.

    Args:
        message: A betterproto message to encode.

    Returns:
        The serialized message prefixed with its length as a 4-byte big-endian integer.
    """
    payload = bytes(message)
    length_prefix = struct.pack(_LENGTH_PREFIX_FORMAT, len(payload))
    return length_prefix + payload


async def read_exact(stream: ByteReceiveStream, num_bytes: int) -> bytes:
    """Read exactly num_bytes from the stream.

    Args:
        stream: An async byte stream to read from.
        num_bytes: The exact number of bytes to read.

    Returns:
        Exactly num_bytes of data.

    Raises:
        FramingError: If the stream closes before num_bytes are read.
    """
    chunks: list[bytes] = []
    bytes_remaining = num_bytes

    while bytes_remaining > 0:
        chunk = await stream.receive(bytes_remaining)
        if not chunk:
            received = num_bytes - bytes_remaining
            raise FramingError(expected_bytes=num_bytes, received_bytes=received)
        chunks.append(chunk)
        bytes_remaining -= len(chunk)

    return b"".join(chunks)


async def read_framed_message(stream: ByteReceiveStream) -> bytes:
    """Read a length-prefixed message from the stream.

    Reads a 4-byte big-endian length prefix, then reads that many bytes as the payload.

    Args:
        stream: An async byte stream to read from.

    Returns:
        The message payload (without the length prefix).

    Raises:
        FramingError: If the stream closes before the complete message is read,
            or if the message size exceeds _MAX_MESSAGE_SIZE.
    """
    # Read the 4-byte length prefix
    length_bytes = await read_exact(stream, _LENGTH_PREFIX_SIZE)
    (length,) = struct.unpack(_LENGTH_PREFIX_FORMAT, length_bytes)

    # Validate message size
    if length > _MAX_MESSAGE_SIZE:
        raise FramingError(expected_bytes=_MAX_MESSAGE_SIZE, received_bytes=length)

    # Read the payload
    return await read_exact(stream, length)
