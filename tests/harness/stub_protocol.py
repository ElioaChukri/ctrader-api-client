"""A scripted stand-in for `Protocol`.

Used for the wide API/auth surface, where the interesting behaviour is
"given this response, what does the caller return?" rather than anything to do
with sockets. Connection-level behaviour is covered against `FakeServer`
instead.

It subclasses the real `Protocol` and overrides only the two I/O methods, so
handler registration and event dispatch run the production code path rather
than a reimplementation of it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import betterproto

from ctrader_api_client.connection import Protocol, Transport

from .signals import Signal, wait_until


Response = betterproto.Message | Exception
ResponseFactory = Callable[[betterproto.Message], Response]


def _as_received[M: betterproto.Message](message: M) -> M:
    """Re-parse a message so it reports sub-message presence like a real one."""
    return type(message)().parse(bytes(message))


class StubProtocol(Protocol):
    """A `Protocol` whose responses are supplied by the test."""

    def __init__(self) -> None:
        super().__init__(transport=Transport(host="stub.invalid", port=0, use_ssl=False))
        self._responses: dict[type[betterproto.Message], ResponseFactory] = {}
        self._sent: list[betterproto.Message] = []
        self._disconnects = 0
        self._running = True
        self._changed = Signal()
        self._live_handlers = 0

    def on_event[M: betterproto.Message](
        self,
        message_type: type[M],
        handler: Callable[[M], Awaitable[None]],
    ) -> Callable[[], None]:
        """Register as the real protocol does, counting what is still live.

        Counted through the disposer the registration hands back rather than by
        reading the protocol's own bookkeeping, so the harness observes only
        what a caller can.
        """
        dispose = super().on_event(message_type, handler)
        self._live_handlers += 1
        disposed = False

        def undo() -> None:
            nonlocal disposed
            dispose()
            if not disposed:
                disposed = True
                self._live_handlers -= 1

        return undo

    # -------------------------------------------------------------------------
    # Scripting
    # -------------------------------------------------------------------------

    def respond(self, request_type: type[betterproto.Message], response: Response) -> None:
        """Answer `request_type` with a fixed response, or raise it if an exception."""
        self._responses[request_type] = lambda _request: response

    def respond_with(self, request_type: type[betterproto.Message], factory: ResponseFactory) -> None:
        """Answer `request_type` with a per-request computed response."""
        self._responses[request_type] = factory

    def respond_in_sequence(
        self,
        request_type: type[betterproto.Message],
        responses: list[Response],
    ) -> None:
        """Answer successive requests of a type with successive responses.

        The final entry is reused once the list is exhausted, so a test can
        script "fail twice, then succeed" without counting exact retries.
        """
        remaining = list(responses)

        def factory(_request: betterproto.Message) -> Response:
            return remaining.pop(0) if len(remaining) > 1 else remaining[0]

        self._responses[request_type] = factory

    # -------------------------------------------------------------------------
    # Observation
    # -------------------------------------------------------------------------

    @property
    def sent(self) -> list[betterproto.Message]:
        """Every message handed to the protocol for transmission."""
        return list(self._sent)

    @property
    def disconnect_count(self) -> int:
        """How many times disconnect handling was triggered."""
        return self._disconnects

    @property
    def handler_count(self) -> int:
        """How many event handlers have been registered and not disposed."""
        return self._live_handlers

    def clear_sent(self) -> None:
        """Forget what has been sent so far, to observe only what follows."""
        self._sent.clear()

    def sent_of[M: betterproto.Message](self, message_type: type[M]) -> list[M]:
        """Every transmitted message of the given type."""
        return [message for message in self._sent if isinstance(message, message_type)]

    def only_sent[M: betterproto.Message](self, message_type: type[M]) -> M:
        """The single transmitted message of the given type.

        Raises:
            AssertionError: If there is not exactly one.
        """
        matches = self.sent_of(message_type)
        if len(matches) != 1:
            raise AssertionError(f"expected exactly one {message_type.__name__}, sent {len(matches)}")
        return matches[0]

    async def emit(self, message: betterproto.Message) -> None:
        """Deliver a server-initiated message to registered handlers.

        The message is round-tripped through its wire encoding first, so
        handlers see exactly what a real connection would hand them. This
        matters for absent sub-messages: a locally built message reports them
        differently from a parsed one.
        """
        await self._dispatch_event(_as_received(message))

    async def wait_for_sent(
        self,
        message_type: type[betterproto.Message],
        count: int = 1,
        timeout: float = 5.0,
    ) -> None:
        """Block until `count` messages of the given type have been transmitted."""
        await wait_until(lambda: len(self.sent_of(message_type)) >= count, self._changed, timeout)

    # -------------------------------------------------------------------------
    # Protocol overrides
    # -------------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Always connected; connection loss is covered against FakeServer."""
        return self._running

    async def send_request(
        self,
        message: betterproto.Message,
        timeout: float = 30.0,  # noqa: ARG002 - part of the interface being stood in for
    ) -> betterproto.Message:
        """Record the request and return the scripted response."""
        self._sent.append(message)
        self._changed.notify()

        factory = self._responses.get(type(message))
        if factory is None:
            raise AssertionError(
                f"no response scripted for {type(message).__name__}; "
                f"call respond({type(message).__name__}, ...) in the test"
            )

        response = factory(message)
        if isinstance(response, Exception):
            raise response
        return _as_received(response)

    async def send_event(self, message: betterproto.Message) -> None:
        """Record a fire-and-forget message."""
        self._sent.append(message)
        self._changed.notify()

    async def handle_disconnect(self) -> None:
        """Record that disconnect handling was triggered."""
        self._disconnects += 1
