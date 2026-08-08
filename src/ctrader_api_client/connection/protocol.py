from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

import anyio
import anyio.abc
import betterproto
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    stop_never,
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
    CTraderReconnectAbandonedError,
    FramingError,
)
from .listener import ConnectionListener
from .transport import Transport


logger = logging.getLogger(__name__)

T = TypeVar("T", bound=betterproto.Message)
EventHandler = Callable[[T], Awaitable[None]]

# Guards for the reader loop's per-message error path. A failure that repeats on
# every iteration (rather than affecting a single message) must not be allowed to
# spin: the backoff yields control so cancellation can be delivered, and the cap
# escalates a stuck reader to a reconnection instead of an endless log flood.
_READ_ERROR_BACKOFF = 0.05
_MAX_CONSECUTIVE_READ_ERRORS = 10


@dataclass(slots=True)
class _PendingRequest:
    """A request awaiting its correlated response.

    Attributes:
        event: Set once the outcome is known, or when the protocol stops.
        outcome: The response, the error the server replied with, or None while
            the request is still in flight. None after the event is set means
            the wait was interrupted by shutdown rather than answered.
    """

    event: anyio.Event
    outcome: betterproto.Message | Exception | None = None


class Protocol:
    """Message-level protocol handling with correlation and dispatch.

    Manages the reader loop, request/response correlation, event dispatch,
    and automatic reconnection with exponential backoff.
    """

    def __init__(
        self,
        transport: Transport,
        reconnect_attempts: int | None = None,
        reconnect_min_wait: float = 1.0,
        reconnect_max_wait: float = 60.0,
    ) -> None:
        """Initialize the protocol handler.

        Args:
            transport: The underlying transport for sending/receiving data.
            reconnect_attempts: Maximum reconnection attempts. None retries for
                as long as the client is open, which is the default: an outage
                that outlasts a finite budget otherwise leaves a client that
                can never recover. 0 disables reconnection entirely.
            reconnect_min_wait: Initial wait between attempts (seconds).
            reconnect_max_wait: Maximum wait between attempts (seconds).
        """
        self._transport = transport
        self._id_generator = ClientMessageIdGenerator()

        # Request correlation
        self._pending: dict[str, _PendingRequest] = {}

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

        # Set when the link drops again while a reconnection is already in
        # flight. The detector that saw it cannot start its own reconnection,
        # so the one already running goes round again on its behalf.
        self._redo_requested = False

        # Told about link transitions; set by whoever owns this protocol.
        self._listener: ConnectionListener | None = None

    def set_listener(self, listener: ConnectionListener) -> None:
        """Register the party told when the link drops and when it comes back.

        Args:
            listener: Normally the `ConnectionSupervisor` that owns this
                protocol. Told before reconnection is attempted so it can
                discard state that only holds while the link is up, and again
                once the transport is back so it can re-establish it.
        """
        self._listener = listener

    @property
    def is_connected(self) -> bool:
        """Whether protocol is connected and reader is running."""
        return self._transport.is_connected and self._running

    async def serve(self, *, task_status: anyio.abc.TaskStatus[None] = anyio.TASK_STATUS_IGNORED) -> None:
        """Run the reader and everything it spawns, until stopped or cancelled.

        Start this with `TaskGroup.start` after `transport.connect()`; it
        reports itself started once the reader is live, so the caller does not
        resume before it is safe to send.

        Raises:
            RuntimeError: If the protocol is already being served.
        """
        if self._running:
            raise RuntimeError("Protocol is already running")

        self._running = True
        try:
            async with anyio.create_task_group() as task_group:
                self._task_group = task_group
                task_group.start_soon(self._reader_loop)
                task_status.started()
        finally:
            self._running = False
            self._task_group = None
            self._reader_scope = None
            self._fail_pending("Connection closed")

    async def stop(self) -> None:
        """Ask the reader and its spawned work to wind down."""
        self._running = False

        if self._reader_scope is not None:
            self._reader_scope.cancel()

        if self._task_group is not None:
            self._task_group.cancel_scope.cancel()

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

        # Create the correlation slot for this request
        pending = _PendingRequest(event=anyio.Event())
        self._pending[msg_id] = pending

        try:
            # Lock write and send message
            async with self._write_lock:
                encoded = encode_with_length_prefix(wrapped)
                await self._transport.send(encoded)

            # Wait for response
            with anyio.fail_after(timeout):
                await pending.event.wait()

            # Check if we were stopped
            if not self._running:
                raise CTraderConnectionClosedError("Protocol stopped while waiting for response")

            # An unresolved outcome means the wait was broken by shutdown
            # rather than answered.
            if pending.outcome is None:
                raise CTraderConnectionClosedError("Protocol stopped while waiting for response")

            if isinstance(pending.outcome, Exception):
                raise pending.outcome

            return pending.outcome

        except TimeoutError:
            raise CTraderConnectionTimeoutError(timeout, "request") from None
        finally:
            self._pending.pop(msg_id, None)

    async def request[R: betterproto.Message](
        self,
        message: betterproto.Message,
        response_type: type[R],
        timeout: float = 30.0,
    ) -> R:
        """Send a request and return its response, narrowed to the expected type.

        Args:
            message: The protobuf message to send.
            response_type: The response the server is expected to reply with.
            timeout: Timeout in seconds for waiting for a response.

        Returns:
            The response message, typed as `response_type`.

        Raises:
            APIError: If the server returns ProtoOAErrorRes, or replies with a
                message of any other type.
            CTraderConnectionClosedError: If not connected and reconnection fails.
            CTraderConnectionTimeoutError: If response not received within timeout.
        """
        response = await self.send_request(message, timeout=timeout)

        if not isinstance(response, response_type):
            raise APIError(
                error_code="UNEXPECTED_RESPONSE",
                description=f"Expected {response_type.__name__}, got {type(response).__name__}",
            )

        return response

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

    def on_event(self, message_type: type[T], handler: EventHandler[T]) -> Callable[[], None]:
        """Register async handler for event type.

        Multiple handlers can be registered for the same event type.

        Args:
            message_type: The protobuf message type to handle.
            handler: Async callable that receives the message.

        Returns:
            A callable that unregisters this handler. Callers that register and
            unregister in different places should keep this instead of naming
            the type and handler a second time.
        """
        if message_type not in self._event_handlers:
            self._event_handlers[message_type] = []
        self._event_handlers[message_type].append(handler)

        def dispose() -> None:
            self.remove_handler(message_type, handler)

        return dispose

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
            consecutive_errors = 0
            while self._running:
                try:
                    raw = await read_framed_message(self._transport.stream)
                    proto_msg = deserialize_proto_message(raw)
                    inner = unwrap_message(proto_msg)
                    await self._dispatch_message(proto_msg, inner)
                    consecutive_errors = 0
                except FramingError as e:
                    logger.error("Protocol framing error (possible data corruption): %s", e)
                    if self._running:
                        await self.handle_disconnect()
                    break
                except (
                    anyio.ClosedResourceError,
                    anyio.EndOfStream,
                    anyio.BrokenResourceError,
                ):
                    # The socket/TLS session is gone. BrokenResourceError leaves
                    # the stream object in place, so retrying would re-raise
                    # immediately — never loop on these.
                    if self._running:
                        logger.debug("Connection closed by remote")
                        await self.handle_disconnect()
                    break
                except CTraderConnectionClosedError:
                    # The transport was closed underneath us: this is a stale
                    # reader still alive while _reconnect_task rebuilds the
                    # connection. That task restarts the reader, so just exit.
                    logger.debug("Reader stopping: transport is no longer connected")
                    break
                except anyio.get_cancelled_exc_class():
                    raise
                except Exception as e:
                    # Genuine per-message errors are recoverable, so keep
                    # reading — but yield first. Without a checkpoint here, an
                    # error that repeats every iteration turns this into a hot
                    # loop that floods the log and starves cancellation.
                    consecutive_errors += 1
                    logger.warning(
                        "Error processing message (%d consecutive): %s: %s",
                        consecutive_errors,
                        type(e).__name__,
                        e,
                        exc_info=consecutive_errors == 1,
                    )
                    if consecutive_errors >= _MAX_CONSECUTIVE_READ_ERRORS:
                        logger.error(
                            "Reader failed %d times consecutively, treating as disconnect",
                            consecutive_errors,
                        )
                        if self._running:
                            await self.handle_disconnect()
                        break
                    await anyio.sleep(_READ_ERROR_BACKOFF)

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
        pending = self._pending.get(msg_id) if msg_id else None
        if pending is not None:
            pending.outcome = APIError.from_proto(inner) if isinstance(inner, ProtoOAErrorRes) else inner
            pending.event.set()
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

        Idempotent: calls made while a reconnection is already in flight do not
        start a second one, so the reader and heartbeat loops racing to report
        the same drop only produce a single reconnection. Such a call is still
        recorded, because it may be reporting a *fresh* drop of the link the
        running reconnection just restored — and the caller cannot retry for
        itself, since the reader loop exits as soon as it has reported.
        """
        if not self._running:
            return
        if self._reconnecting:
            self._redo_requested = True
            return
        if self._task_group is None:
            return

        self._reconnecting = True
        logger.warning("Connection lost, attempting to reconnect...")

        # State tied to the dead link is invalid from this moment on. Report it
        # before reconnecting so nothing observes a session that no longer exists.
        await self._notify_connection_lost()

        self._task_group.start_soon(self._reconnect_task)

    async def _notify_connection_lost(self) -> None:
        """Tell the listener the link is gone.

        Never lets a failing listener block the reconnection: whatever
        bookkeeping it does matters less than getting the link back.
        """
        if self._listener is None:
            return

        try:
            await self._listener.on_connection_lost()
        except Exception:
            logger.exception("Connection listener failed on disconnect")

    async def _reconnect_task(self) -> None:
        """Own the full reconnection lifecycle from a standalone task.

        Runs outside the reader/heartbeat cancel scopes so it survives the death
        of whichever task detected the drop. It must never let an exception
        escape: an unhandled error here would propagate into the protocol task
        group and tear down every other task. A terminal reconnection failure is
        instead recorded by stopping the protocol and waking pending requests.

        Loops rather than running once, so a link that drops again while this is
        working — reported through `handle_disconnect` as `_redo_requested`, the
        only route left once the reader has exited — is reconnected too instead
        of being stranded.

        Raises:
            CTraderReconnectAbandonedError: If reconnection is given up on. This
                is deliberately allowed to escape into the protocol task group
                and tear the client down: see :meth:`_abandon`.
        """
        try:
            while True:
                self._redo_requested = False

                # The reader loop is reading a dead stream; cancel it before we
                # reconnect so a stale reader can't race the fresh one we restart.
                if self._reader_scope is not None:
                    self._reader_scope.cancel()
                    self._reader_scope = None

                # Close the old transport (idempotent — the task that detected
                # the drop may have already raced us to it). Tearing down a dead
                # socket can fail on its own, which says nothing about whether
                # reconnecting will work: swallow it here so it can never be
                # mistaken below for an exhausted reconnection.
                try:
                    await self._transport.close()
                except Exception:
                    logger.debug("Ignoring error while closing dead transport", exc_info=True)

                await self._reconnect()
                logger.info("Reconnection successful")

                if not self._redo_requested:
                    break

                logger.warning("Connection lost again while reconnecting, retrying...")
                # The sessions this pass just restored died with the link that
                # dropped underneath it, so report that loss before going round
                # again — nothing else will, since `handle_disconnect` only
                # recorded the drop rather than handling it.
                await self._notify_connection_lost()
        except (CTraderConnectionFailedError, CTraderConnectionClosedError) as e:
            logger.error("Reconnection failed, giving up: %s", e)
            self._abandon("connection lost and reconnection failed", e)
        except Exception as e:
            # Nothing here is expected to fail this way — the retry loop below
            # absorbs every failure connecting — so treat it as a defect rather
            # than a state to sit quietly in.
            logger.exception("Unexpected error while reconnecting")
            self._abandon("unexpected error while reconnecting", e)
        finally:
            self._reconnecting = False
            self._redo_requested = False

    def _abandon(self, reason: str, cause: BaseException) -> None:
        """Stop the protocol and make giving up impossible to miss.

        A client that has stopped reconnecting cannot recover on its own: the
        reader has exited, the heartbeat loop returns as soon as its next write
        fails, and `handle_disconnect` refuses everything once `_running` is
        False. Nothing is left that could try again. Staying alive in that state
        only means a consumer polling `is_connected` sees a link that is down
        and assumes, reasonably and wrongly, that something is working on it.

        So the failure is raised instead of recorded. It escapes into the
        protocol task group, through the supervisor's, and out of the
        `async with client:` block, where a process supervisor will see it.

        Raises:
            CTraderReconnectAbandonedError: Always, unless reconnection was
                disabled by configuration, which is a choice rather than a
                failure and keeps the previous behaviour of a client that
                rejects further requests.
        """
        self._running = False
        # Wake all pending requests so callers fail fast instead of hanging.
        self._fail_pending(reason)

        if self._reconnect_attempts == 0:
            return

        raise CTraderReconnectAbandonedError(reason, cause) from cause

    def _fail_pending(self, reason: str) -> None:
        """Resolve every in-flight request with a connection error."""
        for pending in self._pending.values():
            pending.outcome = CTraderConnectionClosedError(reason)
            pending.event.set()

    async def _reconnect(self) -> None:
        """Attempt reconnection with exponential backoff.

        Retries on *any* failure rather than on an enumerated set of exception
        types. The budget exists to outlast a server that cannot be reached,
        and an unrecognised exception is no evidence that it can be: a
        whitelist here meant an exception nobody had thought of skipped the
        retries entirely and went straight to being fatal.

        Raises:
            CTraderConnectionClosedError: If reconnection is disabled.
            CTraderConnectionFailedError: If every attempt in the budget failed.
        """
        if self._reconnect_attempts == 0:
            raise CTraderConnectionClosedError("Connection lost and reconnection disabled")

        budget = "unlimited" if self._reconnect_attempts is None else self._reconnect_attempts

        async for attempt in AsyncRetrying(
            stop=stop_never if self._reconnect_attempts is None else stop_after_attempt(self._reconnect_attempts),
            wait=wait_exponential(
                min=self._reconnect_min_wait,
                max=self._reconnect_max_wait,
            ),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                logger.debug(
                    "Reconnection attempt %d/%s",
                    attempt.retry_state.attempt_number,
                    budget,
                )
                await self._transport.connect()

        # Restart the reader loop
        if self._task_group is not None:
            self._task_group.start_soon(self._reader_loop)

        # Report the recovery so server-side state can be re-established. The
        # transport is already back up at this point, so a failure here must not
        # fail the reconnection itself — log it and let the listener's own
        # reporting surface the details.
        if self._listener is not None:
            try:
                await self._listener.on_connection_restored()
            except Exception:
                logger.exception("Connection listener failed on reconnect")
