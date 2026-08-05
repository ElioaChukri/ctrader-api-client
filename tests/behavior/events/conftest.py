"""Shared wiring for event tests."""

from __future__ import annotations

import pytest

from ctrader_api_client.events import EventEmitter, EventRouter

from ...harness import RecordingRecovery, StubProtocol


@pytest.fixture
def recovery() -> RecordingRecovery:
    """Stands in for the auth manager the router hands dropped sessions to."""
    return RecordingRecovery()


@pytest.fixture
def emitter() -> EventEmitter:
    return EventEmitter()


@pytest.fixture
def routing(
    protocol: StubProtocol,
    emitter: EventEmitter,
    recovery: RecordingRecovery,
) -> EventEmitter:
    """A started router feeding the emitter from proto messages on the protocol."""
    router = EventRouter(protocol=protocol, emitter=emitter, recovery=recovery)
    router.start()
    return emitter
