"""Framing and message-envelope rules that the whole protocol depends on."""

from __future__ import annotations

import struct
import threading

import pytest
from anyio.abc import ByteReceiveStream

from ctrader_api_client._internal.messages import (
    ClientMessageIdGenerator,
    deserialize_proto_message,
    unwrap_message,
    wrap_message,
)
from ctrader_api_client._internal.proto import (
    ProtoMessage,
    ProtoOAApplicationAuthReq,
    ProtoOAExecutionEvent,
    ProtoOANewOrderReq,
    ProtoOASpotEvent,
    ProtoOATraderReq,
)
from ctrader_api_client._internal.serialization import encode_with_length_prefix, read_framed_message
from ctrader_api_client.exceptions import DeserializationError, FramingError, UnknownPayloadTypeError


ONE_MEGABYTE = 1024 * 1024


class ChunkStream(ByteReceiveStream):
    """A byte stream that hands out preset chunks, then reports end of data."""

    def __init__(self, *chunks: bytes) -> None:
        self._chunks = list(chunks)

    async def receive(self, max_bytes: int = 65536) -> bytes:
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        if len(chunk) > max_bytes:
            self._chunks.insert(0, chunk[max_bytes:])
            return chunk[:max_bytes]
        return chunk

    async def aclose(self) -> None:
        self._chunks.clear()


def in_chunks(data: bytes, size: int) -> ChunkStream:
    """Split data into fixed-size chunks, as a slow network would."""
    return ChunkStream(*(data[index : index + size] for index in range(0, len(data), size)))


async def test_a_frame_is_prefixed_with_its_payload_length() -> None:
    frame = encode_with_length_prefix(ProtoOATraderReq(ctid_trader_account_id=1))

    (declared_length,) = struct.unpack(">I", frame[:4])

    assert declared_length == len(frame) - 4


async def test_a_frame_reads_back_as_the_payload_that_was_written() -> None:
    message = ProtoOATraderReq(ctid_trader_account_id=99)
    frame = encode_with_length_prefix(message)

    payload = await read_framed_message(ChunkStream(frame))

    assert payload == bytes(message)


async def test_a_payload_split_across_packets_is_reassembled() -> None:
    message = ProtoOAApplicationAuthReq(client_id="a-fairly-long-client-id", client_secret="secret")
    frame = encode_with_length_prefix(message)

    payload = await read_framed_message(in_chunks(frame, 1))

    assert payload == bytes(message)


async def test_only_one_frame_is_consumed_per_read() -> None:
    first = encode_with_length_prefix(ProtoOATraderReq(ctid_trader_account_id=1))
    second = encode_with_length_prefix(ProtoOATraderReq(ctid_trader_account_id=2))
    stream = ChunkStream(first + second)

    assert await read_framed_message(stream) == first[4:]
    assert await read_framed_message(stream) == second[4:]


async def test_a_length_beyond_the_size_limit_is_refused() -> None:
    """An absurd length means the stream is desynchronised, not that a huge message is coming."""
    stream = ChunkStream(struct.pack(">I", ONE_MEGABYTE + 1))

    with pytest.raises(FramingError):
        await read_framed_message(stream)


async def test_a_truncated_payload_is_refused() -> None:
    stream = ChunkStream(struct.pack(">I", 10) + b"abcd")

    with pytest.raises(FramingError):
        await read_framed_message(stream)


async def test_a_truncated_length_prefix_is_refused() -> None:
    stream = ChunkStream(b"\x00\x00")

    with pytest.raises(FramingError):
        await read_framed_message(stream)


@pytest.mark.parametrize(
    ("message_type", "payload_type"),
    [
        (ProtoOAApplicationAuthReq, 2100),
        (ProtoOANewOrderReq, 2106),
        (ProtoOATraderReq, 2121),
        (ProtoOAExecutionEvent, 2126),
        (ProtoOASpotEvent, 2131),
    ],
)
def test_a_message_is_wrapped_with_the_payload_type_the_server_expects(
    message_type: type,
    payload_type: int,
) -> None:
    """These numbers are the wire contract; changing one silently breaks the API."""
    wrapper = wrap_message(message_type())

    assert wrapper.payload_type == payload_type


def test_wrapping_and_unwrapping_preserves_the_message() -> None:
    original = ProtoOANewOrderReq(ctid_trader_account_id=42, symbol_id=270, volume=100_000)

    restored = unwrap_message(wrap_message(original))

    assert restored == original


def test_the_correlation_id_survives_wrapping() -> None:
    wrapper = wrap_message(ProtoOATraderReq(), client_msg_id="request-7")

    assert wrapper.client_msg_id == "request-7"


def test_an_unwrapped_message_has_no_correlation_id_by_default() -> None:
    wrapper = wrap_message(ProtoOATraderReq())

    assert wrapper.client_msg_id == ""


def test_a_message_type_outside_the_registry_cannot_be_sent() -> None:
    with pytest.raises(UnknownPayloadTypeError):
        wrap_message(ProtoMessage())


def test_an_unrecognised_payload_type_is_reported() -> None:
    with pytest.raises(UnknownPayloadTypeError):
        unwrap_message(ProtoMessage(payload_type=64999, payload=b""))


def test_a_corrupt_payload_is_reported_as_a_deserialization_failure() -> None:
    wrapper = ProtoMessage(payload_type=2131, payload=b"\xff\xff\xff\xff\xff")

    with pytest.raises(DeserializationError):
        unwrap_message(wrapper)


def test_garbage_bytes_are_not_accepted_as_an_envelope() -> None:
    with pytest.raises(DeserializationError):
        deserialize_proto_message(b"\xff\xff\xff\xff\xff")


def test_correlation_ids_are_never_reused() -> None:
    generator = ClientMessageIdGenerator()

    ids = [generator.next_id() for _ in range(1000)]

    assert len(set(ids)) == 1000


def test_correlation_ids_stay_unique_under_concurrent_use() -> None:
    """Requests are sent from many tasks and threads; a collision misroutes a response."""
    generator = ClientMessageIdGenerator()
    collected: list[list[str]] = []

    def take_ids() -> None:
        collected.append([generator.next_id() for _ in range(500)])

    threads = [threading.Thread(target=take_ids) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    everything = [msg_id for batch in collected for msg_id in batch]

    assert len(set(everything)) == len(everything) == 4000
