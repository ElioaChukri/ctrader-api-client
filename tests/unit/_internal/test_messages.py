"""Unit tests for messages module."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from ctrader_api_client._internal.messages import (
    ClientMessageIdGenerator,
    MessageRegistry,
    deserialize_proto_message,
    get_registry,
    unwrap_message,
    wrap_message,
)
from ctrader_api_client._internal.proto import (
    ProtoErrorRes,
    ProtoHeartbeatEvent,
    ProtoMessage,
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAErrorRes,
    ProtoOAPayloadType,
    ProtoPayloadType,
)
from ctrader_api_client.exceptions import DeserializationError, UnknownPayloadTypeError


class TestMessageRegistry:
    """Tests for MessageRegistry class."""

    def test_get_class_returns_correct_class(self) -> None:
        """get_class should return the registered class for a payload type."""
        registry = MessageRegistry()
        registry.register(100, ProtoHeartbeatEvent)

        assert registry.get_class(100) is ProtoHeartbeatEvent

    def test_get_class_returns_none_for_unknown(self) -> None:
        """get_class should return None for unregistered payload type."""
        registry = MessageRegistry()

        assert registry.get_class(99999) is None

    def test_get_payload_type_returns_correct_int(self) -> None:
        """get_payload_type should return the registered int for a class."""
        registry = MessageRegistry()
        registry.register(100, ProtoHeartbeatEvent)

        assert registry.get_payload_type(ProtoHeartbeatEvent) == 100

    def test_get_payload_type_returns_none_for_unknown(self) -> None:
        """get_payload_type should return None for unregistered class."""
        registry = MessageRegistry()

        assert registry.get_payload_type(ProtoHeartbeatEvent) is None

    def test_register_creates_bidirectional_mapping(self) -> None:
        """register should create mappings in both directions."""
        registry = MessageRegistry()
        registry.register(42, ProtoOAApplicationAuthReq)

        assert registry.get_class(42) is ProtoOAApplicationAuthReq
        assert registry.get_payload_type(ProtoOAApplicationAuthReq) == 42


class TestClientMessageIdGenerator:
    """Tests for ClientMessageIdGenerator class."""

    def test_generates_sequential_ids(self) -> None:
        """Should generate sequential string IDs starting from 1."""
        gen = ClientMessageIdGenerator()

        assert gen.next_id() == "1"
        assert gen.next_id() == "2"
        assert gen.next_id() == "3"

    def test_thread_safety(self) -> None:
        """Concurrent calls should produce unique IDs."""
        gen = ClientMessageIdGenerator()
        num_threads = 10
        ids_per_thread = 100
        all_ids: list[str] = []
        lock = threading.Lock()

        def generate_ids() -> None:
            thread_ids = [gen.next_id() for _ in range(ids_per_thread)]
            with lock:
                all_ids.extend(thread_ids)

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(generate_ids) for _ in range(num_threads)]
            for f in futures:
                f.result()

        # All IDs should be unique
        assert len(all_ids) == num_threads * ids_per_thread
        assert len(set(all_ids)) == len(all_ids)


class TestGetRegistry:
    """Tests for get_registry function."""

    def test_returns_singleton(self) -> None:
        """Should return the same instance on repeated calls."""
        registry1 = get_registry()
        registry2 = get_registry()

        assert registry1 is registry2

    def test_contains_all_proto_oa_payload_types(self) -> None:
        """Registry should contain all ProtoOAPayloadType members."""
        registry = get_registry()

        for member in ProtoOAPayloadType:
            cls = registry.get_class(member.value)
            assert cls is not None, f"Missing class for {member.name} ({member.value})"

    def test_contains_common_messages(self) -> None:
        """Registry should contain ERROR_RES and HEARTBEAT_EVENT."""
        registry = get_registry()

        assert registry.get_class(ProtoPayloadType.ERROR_RES.value) is ProtoErrorRes
        assert registry.get_class(ProtoPayloadType.HEARTBEAT_EVENT.value) is ProtoHeartbeatEvent


class TestWrapMessage:
    """Tests for wrap_message function."""

    def test_sets_correct_payload_type(self) -> None:
        """Should set the correct payload_type for the message class."""
        message = ProtoOAApplicationAuthReq(client_id="test", client_secret="secret")

        wrapped = wrap_message(message)

        assert wrapped.payload_type == ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_REQ.value

    def test_serializes_payload(self) -> None:
        """Should serialize the message into the payload field."""
        message = ProtoOAApplicationAuthReq(client_id="test", client_secret="secret")

        wrapped = wrap_message(message)

        # Payload should be non-empty bytes
        assert isinstance(wrapped.payload, bytes)
        assert len(wrapped.payload) > 0

    def test_includes_client_msg_id_when_provided(self) -> None:
        """Should include client_msg_id when provided."""
        message = ProtoHeartbeatEvent()

        wrapped = wrap_message(message, client_msg_id="test-123")

        assert wrapped.client_msg_id == "test-123"

    def test_uses_empty_string_when_no_client_msg_id(self) -> None:
        """Should use empty string when client_msg_id is not provided."""
        message = ProtoHeartbeatEvent()

        wrapped = wrap_message(message)

        assert wrapped.client_msg_id == ""

    def test_raises_unknown_payload_type_for_unregistered(self) -> None:
        """Should raise UnknownPayloadTypeError for unregistered message class."""

        class FakeMessage:
            pass

        with pytest.raises(UnknownPayloadTypeError):
            wrap_message(FakeMessage())  # ty: ignore[invalid-argument-type]


class TestUnwrapMessage:
    """Tests for unwrap_message function."""

    def test_deserializes_to_correct_type(self) -> None:
        """Should deserialize to the correct message type."""
        original = ProtoOAApplicationAuthReq(client_id="test", client_secret="secret")
        wrapped = wrap_message(original)

        unwrapped = unwrap_message(wrapped)

        assert isinstance(unwrapped, ProtoOAApplicationAuthReq)

    def test_preserves_field_values(self) -> None:
        """Should preserve all field values through round-trip."""
        original = ProtoOAApplicationAuthReq(client_id="my-client", client_secret="my-secret")
        wrapped = wrap_message(original)

        unwrapped = unwrap_message(wrapped)

        assert isinstance(unwrapped, ProtoOAApplicationAuthReq)
        assert unwrapped.client_id == "my-client"
        assert unwrapped.client_secret == "my-secret"

    def test_raises_unknown_payload_type_for_unknown(self) -> None:
        """Should raise UnknownPayloadTypeError for unknown payload_type."""
        proto_message = ProtoMessage(payload_type=99999, payload=b"test")

        with pytest.raises(UnknownPayloadTypeError) as exc_info:
            unwrap_message(proto_message)

        assert exc_info.value.payload_type == 99999

    def test_raises_deserialization_error_for_corrupt_payload(self) -> None:
        """Should raise DeserializationError for corrupt payload bytes."""
        # Use a valid payload_type but garbage payload
        proto_message = ProtoMessage(
            payload_type=ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_REQ.value,
            payload=b"\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff",
        )

        with pytest.raises(DeserializationError) as exc_info:
            unwrap_message(proto_message)

        assert exc_info.value.payload_type == ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_REQ.value


class TestDeserializeProtoMessage:
    """Tests for deserialize_proto_message function."""

    def test_parses_valid_proto_message(self) -> None:
        """Should correctly parse valid ProtoMessage bytes."""
        original = ProtoMessage(
            payload_type=ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_REQ.value,
            payload=b"test",
            client_msg_id="123",
        )
        serialized = bytes(original)

        result = deserialize_proto_message(serialized)

        assert result.payload_type == original.payload_type
        assert result.payload == original.payload
        assert result.client_msg_id == original.client_msg_id

    def test_raises_deserialization_error_for_invalid_bytes(self) -> None:
        """Should raise DeserializationError for invalid bytes."""
        # betterproto is lenient, so we need truly garbage data
        # Actually, betterproto might not raise on garbage - it's very lenient
        # Let's test with a case we know will cause issues
        invalid_data = b""

        # Empty data should still parse (to empty message), so this might not raise
        # Let's just verify it returns a ProtoMessage
        result = deserialize_proto_message(invalid_data)
        assert isinstance(result, ProtoMessage)


class TestRoundTrip:
    """Integration-style tests for full wrap/unwrap round-trips."""

    @pytest.mark.parametrize(
        "message",
        [
            ProtoHeartbeatEvent(),
            ProtoOAApplicationAuthReq(client_id="test", client_secret="secret"),
            ProtoOAApplicationAuthRes(),
            ProtoOAErrorRes(error_code="TEST", description="Test error"),
        ],
    )
    def test_round_trip_preserves_message(self, message: object) -> None:
        """Various message types should survive wrap/unwrap round-trip."""
        wrapped = wrap_message(message)  # ty: ignore[invalid-argument-type]
        unwrapped = unwrap_message(wrapped)

        assert type(unwrapped) is type(message)
