"""Shared wiring for event tests."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from ctrader_api_client.events import EventEmitter, EventRouter
from ctrader_api_client.events.emitter import ErrorHandler

from ...harness import StubProtocol


@pytest.fixture
def make_emitter() -> Callable[..., EventEmitter]:
    """Build emitters, optionally with an error handler."""

    def factory(on_handler_error: ErrorHandler | None = None) -> EventEmitter:
        return EventEmitter(on_handler_error=on_handler_error)

    return factory


@pytest.fixture
def emitter(make_emitter: Callable[..., EventEmitter]) -> EventEmitter:
    return make_emitter()


@pytest.fixture
def routing(protocol: StubProtocol, emitter: EventEmitter) -> EventEmitter:
    """A started router feeding the emitter from proto messages on the protocol."""
    router = EventRouter(protocol=protocol, emitter=emitter)
    router.start()
    return emitter
