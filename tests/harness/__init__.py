"""Shared test harness for the cTrader API client test suite.

The harness exists so that tests never poke at internals or assert on calls.
It provides real(ish) boundaries to push bytes and messages through:

- `FakeServer`  - an in-process TCP server speaking the real wire protocol.
- `StubProtocol` - a scripted stand-in for `Protocol`, for breadth tests.
- `ManualClock`  - deterministic control over time-driven behaviour.
"""

from .clock import ManualClock
from .recorder import FailingRecorder, Recorder
from .server import FakeServer
from .signals import Signal, wait_until
from .stub_protocol import StubProtocol
from .wire import decode_frames, encode_frame, encode_message_frame, payload_type_for, unwrap


__all__ = [
    "FailingRecorder",
    "FakeServer",
    "ManualClock",
    "Recorder",
    "Signal",
    "StubProtocol",
    "ask",
    "decode_frames",
    "encode_frame",
    "encode_message_frame",
    "payload_type_for",
    "unwrap",
    "wait_until",
]
