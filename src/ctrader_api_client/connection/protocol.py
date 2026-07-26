from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

import anyio
import anyio.abc
import betterproto
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .._internal import (
    ClientMessageIdGenerator,
    deserialize_proto_message,
    encode_with_length_prefix,
    read_framed_message,
    unwrap_message,
    wrap_message,
)
from .._internal.proto import ProtoMessage, ProtoOAErrorRes
from ..exceptions import (
    APIError,
    CTraderConnectionClosedError,
    CTraderConnectionFailedError,
    CTraderConnectionTimeoutError,
    FramingError,
)
from .transport import Transport


logger = logging.getLogger(__name__)

T = TypeVar("T", bound=betterproto.Message)
EventHandler = Callable[[T], Awaitable[None]]


class Protocol:
    """Message-level protocol handling with correlation and dispatch.

    Manages the reader loop, request/response correlation, event dispatch,
    and automatic reconnection with exponential backoff.
    """

    def __init__(
        self,
        transport: Transport,
        reconnect_attempts: int = 5,
        reconnect_min_wait: float = 1.0,
        reconnect_max_wait: float = 60.0,
    ) -> None:
        """Initialize the protocol handler.

        Args:
            transport: The underlying transport for sending/receiving data.
            reconnect_attempts: Maximum reconnection attempts (0 to disable).
            reconnect_min_wait: Initial wait between attempts (seconds).
            reconnect_max_wait: Maximum wait between attempts (seconds).
        """
        self._transport = transport
        self._id_generator = ClientMessageIdGenerator()

        # Request correlation
        self._pending: dict[str, anyio.Event] = {}
        self._results: dict[str, betterproto.Message] = {}
        self._errors: dict[str, Exception] = {}

        # Event dispatch
        self._event_handlers: dict[type, list[EventHandler]] = {}

        # Concurrency control
        self._write_lock: anyio.Lock = anyio.Lock()
        self._reader_scope: anyio.CancelScope | None = None
        self._task_group: anyio.abc.TaskGroup | None = None
        self._running = False

        # Reconnection config
        self._reconnect_attempts = reconnect_attempts
        self._reconnect_min_wait = reconnect_min_wait
        self._reconnect_max_wait = reconnect_max_wait

        # Guards against multiple concurrent reconnection attempts (e.g. the
        # reader loop and the heartbeat loop both detecting the same drop).
        self._reconnecting = False

        # Reconnection callback (set by CTraderClient)
        self._on_reconnect: Callable[[], Awaitable[None]] | None = None

    @property
    def is_connected(self) -> bool:
        """Whether protocol is connected and reader is running."""
        return self._transport.is_connected and self._running

    async def start(self) -> None:
        """Start the reader task.

        Call this after transport.connect() to begin reading messages.
        """
        if self._running:
            return

        self._running = True
        self._task_group = anyio.create_task_group()
        await self._task_group.__aenter__()
        self._task_group.start_soon(self._reader_loop)

    async def stop(self) -> None:
        """Stop the reader task gracefully."""
        self._running = False

        if self._reader_scope is not None:
            self._reader_scope.cancel()

        if self._task_group is not None:
            self._task_group.cancel_scope.cancel()
            try:
                await self._task_group.__aexit__(None, None, None)
            except Exception:
                pass
            self._task_group = None

        # Signal all pending requests to wake up
        for event in self._pending.values():
            event.set()

    async def send_request(
        self,
        message: betterproto.Message,
        timeout: float = 30.0,
    ) -> betterproto.Message:
        """Send request and wait for correlated response.

        Args:
            message: The protobuf message to send.
            timeout: Timeout in seconds for waiting for a response.

        Returns:
            The response message from the server.

        Raises:
            CTraderConnectionClosedError: If not connected and reconnection fails.
            CTraderConnectionTimeoutError: If response not received within timeout.
            APIError: If server returns ProtoOAErrorRes.
        """
        if not self._running:
            raise CTraderConnectionClosedError("Protocol not running")

        msg_id = self._id_generator.next_id()
        wrapped = wrap_message(message, client_msg_id=msg_id)

        # Create event for this request
        event = anyio.Event()
        self._pending[msg_id] = event

        try:
            # Lock write and send message
            async with self._write_lock:
                encoded = encode_with_length_prefix(wrapped)
                await self._transport.send(encoded)

            # Wait for response
            with anyio.fail_after(timeout):
                await event.wait()

            # Check if we were stopped
            if not self._running:
                raise CTraderConnectionClosedError("Protocol stopped while waiting for response")

            # Check for error response
            if msg_id in self._errors:
                raise self._errors.pop(msg_id)

            return self._results.pop(msg_id)

        except TimeoutError:
            raise CTraderConnectionTimeoutError(timeout, "request") from None
        finally:
            self._pending.pop(msg_id, None)
            self._results.pop(msg_id, None)
            self._errors.pop(msg_id, None)

    async def send_event(self, message: betterproto.Message) -> None:
        """Send message without expecting response (e.g., heartbeat).

        Args:
            message: The protobuf message to send.

        Raises:
            CTraderConnectionClosedError: If not connected.
        """
        if not self._running:
            raise CTraderConnectionClosedError("Protocol not running")

        wrapped = wrap_message(message)

        async with self._write_lock:
            encoded = encode_with_length_prefix(wrapped)
            await self._transport.send(encoded)

    def on_event(self, message_type: type[T], handler: EventHandler[T]) -> None:
        """Register async handler for event type.

        Multiple handlers can be registered for the same event type.

        Args:
            message_type: The protobuf message type to handle.
            handler: Async callable that receives the message.
        """
        if message_type not in self._event_handlers:
            self._event_handlers[message_type] = []
        self._event_handlers[message_type].append(handler)

    def remove_handler(self, message_type: type[T], handler: EventHandler[T]) -> None:
        """Remove previously registered handler.

        Fails silently if handler not found.

        Args:
            message_type: The protobuf message type.
            handler: The handler to remove.
        """
        if message_type in self._event_handlers:
            try:
                self._event_handlers[message_type].remove(handler)
            except ValueError:
                pass  # Handler not found

    async def _reader_loop(self) -> None:
        """Continuously read and dispatch messages until stopped."""
        with anyio.CancelScope() as scope:
            self._reader_scope = scope
            while self._running:
                try:
                    raw = await read_framed_message(self._transport.stream)
                    proto_msg = deserialize_proto_message(raw)
                    inner = unwrap_message(proto_msg)
                    await self._dispatch_message(proto_msg, inner)
                except FramingError as e:
                    logger.error("Protocol framing error (possible data corruption): %s", e)
                    if self._running:
                        await self.handle_disconnect()
                    break
                except (anyio.ClosedResourceError, anyio.EndOfStream):
                    if self._running:
                        logger.debug("Connection closed by remote")
                        await self.handle_disconnect()
                    break
                except anyio.get_cancelled_exc_class():
                    break
                except Exception as e:
                    # Log but continue - don't crash reader on single message errors
                    logger.warning("Error processing message: %s", e)
                    continue

    async def _dispatch_message(
        self,
        proto_msg: ProtoMessage,
        inner: betterproto.Message,
    ) -> None:
        """Route message to pending request or event handlers.

        Args:
            proto_msg: The wrapper message containing client_msg_id.
            inner: The unwrapped inner message.
        """
        msg_id = proto_msg.client_msg_id

        # Check if this is a response to a pending request
        if msg_id and msg_id in self._pending:
            if isinstance(inner, ProtoOAErrorRes):
                self._errors[msg_id] = APIError.from_proto(inner)
            else:
                self._results[msg_id] = inner
            self._pending[msg_id].set()
        else:
            # Server-initiated event
            await self._dispatch_event(inner)

    async def _dispatch_event(self, message: betterproto.Message) -> None:
        """Spawn tasks for registered handlers of this event type.

        Handlers are spawned as concurrent tasks to prevent deadlocks if
        handlers perform some blocking I/O calls that require responses from the reader loop.
        Walks the MRO so handlers registered for a base class (e.g. betterproto.Message)
        are also called for all subclass messages.

        Args:
            message: The event message to dispatch.
        """
        for cls in type(message).__mro__:
            handlers = self._event_handlers.get(cls, [])
            for handler in handlers:
                if self._task_group is not None:
                    self._task_group.start_soon(self._call_handler_safe, handler, message)
                else:
                    # Fallback if task group not available (shouldn't happen in normal operation)
                    await self._call_handler_safe(handler, message)

    @staticmethod
    async def _call_handler_safe(
        handler: EventHandler,
        message: betterproto.Message,
    ) -> None:
        """Call an event handler with exception safety.

        Args:
            handler: The handler to call.
            message: The message to pass to the handler.
        """
        try:
            await handler(message)
        except Exception as e:
            # Log but don't crash - other handlers should still run
            logger.warning("Event handler error: %s", e)

    async def handle_disconnect(self) -> None:
        """Trigger reconnection after an unexpected disconnect.

        Safe to call from any task — the reader loop, the heartbeat loop, or a
        failed heartbeat write. The reconnection itself runs as a *separate*
        task on the protocol task group (see :meth:`_reconnect_task`) rather
        than inline.

        This indirection is essential: the caller is usually the reader loop,
        which invokes this method from inside its own ``anyio.CancelScope``.
        Doing the reconnection inline used to cancel that scope (to stop the
        reader) and thereby abort the in-flight reconnection at its very first
        checkpoint, leaving the client permanently offline. Spawning a
        standalone task decouples the reconnection from the cancel scope of
        whichever loop detected the drop.

        Idempotent: calls made while a reconnection is already in flight are
        ignored, so the reader and heartbeat loops racing to report the same
        drop only produce a single reconnection.
        """
        if not self._running or self._reconnecting:
            return
        if self._task_group is None:
            return

        self._reconnecting = True
        logger.warning("Connection lost, attempting to reconnect...")
        self._task_group.start_soon(self._reconnect_task)

    async def _reconnect_task(self) -> None:
        """Own the full reconnection lifecycle from a standalone task.

        Runs outside the reader/heartbeat cancel scopes so it survives the death
        of whichever task detected the drop. It must never let an exception
        escape: an unhandled error here would propagate into the protocol task
        group and tear down every other task. A terminal reconnection failure is
        instead recorded by stopping the protocol and waking pending requests.
        """
        try:
            # The reader loop is reading a dead stream; cancel it before we
            # reconnect so a stale reader can't race the fresh one we restart.
            if self._reader_scope is not None:
                self._reader_scope.cancel()
                self._reader_scope = None

            # Close the old transport (idempotent — the task that detected the
            # drop may have already raced us to it).
            await self._transport.close()

            await self._reconnect()
            logger.info("Reconnection successful")
        except (CTraderConnectionFailedError, CTraderConnectionClosedError) as e:
            logger.error("Reconnection failed, giving up: %s", e)
            self._running = False
            # Wake all pending requests so callers fail fast instead of hanging.
            for msg_id in list(self._pending.keys()):
                self._errors[msg_id] = CTraderConnectionClosedError(
                    "Connection lost and reconnection failed"
                )
                self._pending[msg_id].set()
        except Exception:
            # Defensive: never let the reconnection task crash the task group.
            logger.exception("Unexpected error while reconnecting")
            self._running = False
            for msg_id in list(self._pending.keys()):
                self._errors[msg_id] = CTraderConnectionClosedError("Reconnection error")
                self._pending[msg_id].set()
        finally:
            self._reconnecting = False

    async def _reconnect(self) -> None:
        """Attempt reconnection with exponential backoff.

        Raises:
            CTraderConnectionClosedError: If reconnection is disabled or all attempts fail.
            CTraderConnectionFailedError: If connection cannot be established.
        """
        if self._reconnect_attempts == 0:
            raise CTraderConnectionClosedError("Connection lost and reconnection disabled")

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._reconnect_attempts),
            wait=wait_exponential(
                min=self._reconnect_min_wait,
                max=self._reconnect_max_wait,
            ),
            retry=retry_if_exception_type(CTraderConnectionFailedError),
            reraise=True,
        ):
            with attempt:
                logger.debug(
                    "Reconnection attempt %d/%d",
                    attempt.retry_state.attempt_number,
                    self._reconnect_attempts,
                )
                await self._transport.connect()

        # Restart the reader loop
        if self._task_group is not None:
            self._task_group.start_soon(self._reader_loop)

        # Notify callback for re-authentication. The transport is already back
        # up at this point, so a failure in the callback must not fail the
        # reconnection itself — log it and let the caller's ReconnectedEvent
        # surface the details.
        if self._on_reconnect is not None:
            try:
                await self._on_reconnect()
            except Exception:
                logger.exception("Post-reconnect re-authentication callback failed")
