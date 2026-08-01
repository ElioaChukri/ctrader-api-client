"""An in-process cTrader server speaking the real wire protocol.

Tests drive the real `Transport`, `Protocol`, framing, correlation and
reconnection code against this, over a genuine loopback TCP connection. The
only thing faked is the far end of the socket, so behaviour is exercised
end-to-end without mocks.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from types import TracebackType

import anyio
import anyio.abc
import betterproto
from anyio.abc import SocketAttribute, SocketStream

from ctrader_api_client._internal.proto import ProtoMessage

from .signals import Signal, wait_until
from .wire import decode_frames, encode_message_frame, unwrap


ResponderResult = betterproto.Message | Sequence[betterproto.Message] | None
Responder = Callable[[betterproto.Message], ResponderResult | Awaitable[ResponderResult]]


@dataclass(frozen=True, slots=True)
class ReceivedRequest:
    """A request the server read off the wire."""

    message: betterproto.Message
    client_msg_id: str


class FakeServer:
    """A scripted cTrader server bound to an ephemeral loopback port."""

    def __init__(self) -> None:
        self._responders: dict[type[betterproto.Message], Responder] = {}
        self._received: list[ReceivedRequest] = []
        self._connection_count = 0
        self._stream: SocketStream | None = None
        self._open_streams: list[SocketStream] = []
        self._listener: anyio.abc.Listener[SocketStream] | None = None
        self._task_group: anyio.abc.TaskGroup | None = None
        self._changed = Signal()

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def start(self) -> None:
        """Bind to an ephemeral port and begin accepting connections."""
        self._listener = await anyio.create_tcp_listener(local_host="127.0.0.1")
        self._task_group = anyio.create_task_group()
        await self._task_group.__aenter__()
        self._task_group.start_soon(self._serve)

    async def stop(self) -> None:
        """Close all connections and stop accepting."""
        # Close accepted sockets explicitly. Cancelling the accept loop unwinds
        # anyio's exit stack in an already-cancelled scope, which can skip the
        # close and leak the file descriptor into the next test.
        with anyio.CancelScope(shield=True):
            for stream in self._open_streams:
                with suppress(anyio.ClosedResourceError, anyio.BrokenResourceError, OSError):
                    await stream.aclose()
        self._open_streams.clear()

        # Cancel the accept loop *before* closing the listener: closing it out
        # from under `serve()` surfaces as a ClosedResourceError buried in a
        # task-group ExceptionGroup during teardown.
        if self._task_group is not None:
            self._task_group.cancel_scope.cancel()
            await self._task_group.__aexit__(None, None, None)
            self._task_group = None

        if self._listener is not None:
            await self._listener.aclose()
            self._listener = None

        self._stream = None

    async def __aenter__(self) -> FakeServer:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.stop()

    @property
    def port(self) -> int:
        """The bound port."""
        if self._listener is None:
            raise RuntimeError("server is not started")
        listeners = getattr(self._listener, "listeners", [self._listener])
        address = listeners[0].extra(SocketAttribute.local_address)
        return int(address[1])

    # -------------------------------------------------------------------------
    # Scripting
    # -------------------------------------------------------------------------

    def on[M: betterproto.Message](
        self,
        request_type: type[M],
        responder: Callable[[M], ResponderResult | Awaitable[ResponderResult]],
    ) -> None:
        """Handle `request_type` with a callable.

        The responder receives the decoded request and may return a message, a
        sequence of messages, or None to stay silent (useful for provoking
        client-side timeouts). It may be sync or async.
        """
        self._responders[request_type] = responder  # type: ignore[assignment]

    def respond(
        self,
        request_type: type[betterproto.Message],
        response: betterproto.Message | Sequence[betterproto.Message],
    ) -> None:
        """Always answer `request_type` with a fixed response."""
        self._responders[request_type] = lambda _request: response

    def silence(self, request_type: type[betterproto.Message]) -> None:
        """Accept `request_type` and never answer it."""
        self._responders[request_type] = lambda _request: None

    # -------------------------------------------------------------------------
    # Observation
    # -------------------------------------------------------------------------

    @property
    def received(self) -> list[betterproto.Message]:
        """Every message the server has read, in arrival order."""
        return [entry.message for entry in self._received]

    @property
    def entries(self) -> list[ReceivedRequest]:
        """Every received message paired with its correlation id."""
        return list(self._received)

    @property
    def connection_count(self) -> int:
        """How many connections have been accepted since start."""
        return self._connection_count

    @property
    def is_connected(self) -> bool:
        """Whether a client connection is currently open."""
        return self._stream is not None

    def requests_of[M: betterproto.Message](self, request_type: type[M]) -> list[M]:
        """Every received message of the given type."""
        return [entry.message for entry in self._received if isinstance(entry.message, request_type)]

    async def wait_for_request(
        self,
        request_type: type[betterproto.Message],
        count: int = 1,
        timeout: float = 5.0,
    ) -> None:
        """Block until `count` messages of `request_type` have arrived."""
        await wait_until(
            lambda: len(self.requests_of(request_type)) >= count,
            self._changed,
            timeout,
        )

    async def wait_for_connections(self, count: int = 1, timeout: float = 5.0) -> None:
        """Block until `count` connections have been accepted."""
        await wait_until(lambda: self._connection_count >= count, self._changed, timeout)

    async def wait_for_disconnect(self, timeout: float = 5.0) -> None:
        """Block until no client connection is open."""
        await wait_until(lambda: self._stream is None, self._changed, timeout)

    # -------------------------------------------------------------------------
    # Server-initiated traffic
    # -------------------------------------------------------------------------

    async def push(self, message: betterproto.Message, client_msg_id: str = "") -> None:
        """Send an unsolicited message to the connected client."""
        await self.send_raw(encode_message_frame(message, client_msg_id=client_msg_id))

    async def send_raw(self, data: bytes) -> None:
        """Write raw bytes to the connected client, bypassing framing."""
        stream = self._stream
        if stream is None:
            raise RuntimeError("no client is connected")
        await stream.send(data)

    async def drop_connection(self) -> None:
        """Close the current connection, simulating a dropped link."""
        stream = self._stream
        if stream is None:
            return
        self._stream = None
        if stream in self._open_streams:
            self._open_streams.remove(stream)
        await stream.aclose()
        self._changed.notify()

    # -------------------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------------------

    async def _serve(self) -> None:
        if self._listener is None:
            return
        try:
            await self._listener.serve(self._handle_connection)
        except (anyio.ClosedResourceError, anyio.BrokenResourceError):
            pass

    async def _handle_connection(self, stream: SocketStream) -> None:
        self._connection_count += 1
        self._stream = stream
        self._open_streams.append(stream)
        self._changed.notify()

        buffer = b""
        try:
            while True:
                buffer += await stream.receive()
                frames, buffer = decode_frames(buffer)
                for frame in frames:
                    await self._process(frame)
        except (anyio.EndOfStream, anyio.ClosedResourceError, anyio.BrokenResourceError):
            pass
        finally:
            if self._stream is stream:
                self._stream = None
            if stream in self._open_streams:
                self._open_streams.remove(stream)
            with anyio.CancelScope(shield=True):
                with suppress(anyio.ClosedResourceError, anyio.BrokenResourceError, OSError):
                    await stream.aclose()
            self._changed.notify()

    async def _process(self, frame: ProtoMessage) -> None:
        message = unwrap(frame)
        self._received.append(ReceivedRequest(message=message, client_msg_id=frame.client_msg_id))
        self._changed.notify()

        responder = self._responders.get(type(message))
        if responder is None:
            return

        result = responder(message)
        if inspect.isawaitable(result):
            result = await result
        if result is None:
            return

        responses = [result] if isinstance(result, betterproto.Message) else list(result)
        for response in responses:
            await self.push(response, client_msg_id=frame.client_msg_id)
