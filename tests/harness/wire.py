"""Independent implementation of the cTrader wire format.

The framing here is written from the protocol description (4-byte big-endian
length prefix followed by a serialized `ProtoMessage`) rather than reusing
`ctrader_api_client._internal.serialization`. If the harness shared that code,
framing tests would confirm the implementation against itself and prove
nothing.

The payload-type lookup does reuse the production registry, because
duplicating a hundred-entry table would itself be a source of bugs. That
mapping is pinned independently by the registry tests, so a regression there
fails loudly rather than silently corrupting every other test.
"""

from __future__ import annotations

import struct

import betterproto

from ctrader_api_client._internal import get_class, get_payload_type
from ctrader_api_client._internal.proto import ProtoMessage


LENGTH_PREFIX_FORMAT = ">I"
LENGTH_PREFIX_SIZE = 4


def payload_type_for(message_class: type[betterproto.Message]) -> int:
    """Return the wire payload type for a message class.

    Raises:
        KeyError: If the class is not registered.
    """
    payload_type = get_payload_type(message_class)
    if payload_type is None:
        raise KeyError(f"{message_class.__name__} has no registered payload type")
    return payload_type


def encode_frame(payload_type: int, payload: bytes, client_msg_id: str = "") -> bytes:
    """Build a length-prefixed frame from raw wrapper fields."""
    wrapper = ProtoMessage(
        payload_type=payload_type,
        payload=payload,
        client_msg_id=client_msg_id,
    )
    body = bytes(wrapper)
    return struct.pack(LENGTH_PREFIX_FORMAT, len(body)) + body


def encode_message_frame(message: betterproto.Message, client_msg_id: str = "") -> bytes:
    """Build a length-prefixed frame carrying `message`."""
    return encode_frame(
        payload_type=payload_type_for(type(message)),
        payload=bytes(message),
        client_msg_id=client_msg_id,
    )


def decode_frames(buffer: bytes) -> tuple[list[ProtoMessage], bytes]:
    """Split a byte buffer into complete wrapper messages.

    Args:
        buffer: Accumulated bytes, possibly ending mid-frame.

    Returns:
        A tuple of (complete messages, unconsumed trailing bytes).
    """
    messages: list[ProtoMessage] = []
    offset = 0

    while len(buffer) - offset >= LENGTH_PREFIX_SIZE:
        (length,) = struct.unpack_from(LENGTH_PREFIX_FORMAT, buffer, offset)
        frame_end = offset + LENGTH_PREFIX_SIZE + length
        if len(buffer) < frame_end:
            break
        body = buffer[offset + LENGTH_PREFIX_SIZE : frame_end]
        messages.append(ProtoMessage().parse(body))
        offset = frame_end

    return messages, buffer[offset:]


def unwrap(wrapper: ProtoMessage) -> betterproto.Message:
    """Deserialize the inner message carried by a wrapper.

    Raises:
        KeyError: If the payload type is not registered.
    """
    message_class = get_class(wrapper.payload_type)
    if message_class is None:
        raise KeyError(f"payload type {wrapper.payload_type} is not registered")
    return message_class().parse(wrapper.payload)
