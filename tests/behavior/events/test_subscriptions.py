"""Who receives an emitted event, and who does not."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import anyio
import pytest

from ctrader_api_client.events import (
    ClientDisconnectEvent,
    DepthEvent,
    Event,
    EventEmitter,
    ReadyEvent,
    SpotEvent,
)

from ...harness import FailingRecorder, Recorder, factories


OTHER_SYMBOL_ID = 999


def spot(account_id: int = factories.ACCOUNT_ID, symbol_id: int = factories.SYMBOL_ID) -> SpotEvent:
    return SpotEvent(
        account_id=account_id,
        symbol_id=symbol_id,
        bid=Decimal("1.085"),
        ask=Decimal("1.087"),
        trendbar=[],
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
    )


async def test_a_subscriber_receives_the_emitted_event(emitter: EventEmitter) -> None:
    received: Recorder[SpotEvent] = Recorder()
    emitter.subscribe(SpotEvent, received)

    event = spot()
    await emitter.emit(event)

    assert received.only is event


async def test_a_subscriber_of_another_type_is_left_alone(emitter: EventEmitter) -> None:
    ready: Recorder[ReadyEvent] = Recorder()
    emitter.subscribe(ReadyEvent, ready)

    await emitter.emit(spot())

    assert ready.count == 0


async def test_every_subscriber_of_the_type_receives_the_event(emitter: EventEmitter) -> None:
    first: Recorder[SpotEvent] = Recorder()
    second: Recorder[SpotEvent] = Recorder()
    emitter.subscribe(SpotEvent, first)
    emitter.subscribe(SpotEvent, second)

    await emitter.emit(spot())

    assert (first.count, second.count) == (1, 1)


async def test_an_event_with_no_subscribers_is_dropped(emitter: EventEmitter) -> None:
    await emitter.emit(spot())

    assert emitter.subscription_count() == 0


async def test_an_account_filter_admits_only_that_account(emitter: EventEmitter) -> None:
    received: Recorder[SpotEvent] = Recorder()
    emitter.subscribe(SpotEvent, received, account_id=factories.ACCOUNT_ID)

    await emitter.emit(spot(account_id=factories.OTHER_ACCOUNT_ID))
    await emitter.emit(spot(account_id=factories.ACCOUNT_ID))

    assert received.only.account_id == factories.ACCOUNT_ID


async def test_a_symbol_filter_admits_only_that_symbol(emitter: EventEmitter) -> None:
    received: Recorder[SpotEvent] = Recorder()
    emitter.subscribe(SpotEvent, received, symbol_id=factories.SYMBOL_ID)

    await emitter.emit(spot(symbol_id=OTHER_SYMBOL_ID))
    await emitter.emit(spot(symbol_id=factories.SYMBOL_ID))

    assert received.only.symbol_id == factories.SYMBOL_ID


async def test_both_filters_must_match(emitter: EventEmitter) -> None:
    received: Recorder[SpotEvent] = Recorder()
    emitter.subscribe(
        SpotEvent,
        received,
        account_id=factories.ACCOUNT_ID,
        symbol_id=factories.SYMBOL_ID,
    )

    await emitter.emit(spot(account_id=factories.OTHER_ACCOUNT_ID, symbol_id=factories.SYMBOL_ID))
    await emitter.emit(spot(account_id=factories.ACCOUNT_ID, symbol_id=OTHER_SYMBOL_ID))
    await emitter.emit(spot(account_id=factories.ACCOUNT_ID, symbol_id=factories.SYMBOL_ID))

    assert received.count == 1


async def test_an_unfiltered_subscriber_receives_every_account(emitter: EventEmitter) -> None:
    received: Recorder[SpotEvent] = Recorder()
    emitter.subscribe(SpotEvent, received)

    await emitter.emit(spot(account_id=factories.ACCOUNT_ID))
    await emitter.emit(spot(account_id=factories.OTHER_ACCOUNT_ID))

    assert received.count == 2


async def test_filtering_by_a_field_the_event_lacks_is_rejected(emitter: EventEmitter) -> None:
    """Silently never delivering would be far harder to diagnose than a startup error."""
    received: Recorder[ClientDisconnectEvent] = Recorder()

    with pytest.raises(ValueError, match="account_id"):
        emitter.subscribe(ClientDisconnectEvent, received, account_id=factories.ACCOUNT_ID)


async def test_filtering_by_symbol_on_an_account_only_event_is_rejected(emitter: EventEmitter) -> None:
    received: Recorder[ReadyEvent] = Recorder()

    with pytest.raises(ValueError, match="symbol_id"):
        emitter.subscribe(ReadyEvent, received, symbol_id=factories.SYMBOL_ID)


async def test_a_rejected_filter_leaves_no_subscription_behind(emitter: EventEmitter) -> None:
    received: Recorder[ReadyEvent] = Recorder()

    with pytest.raises(ValueError):
        emitter.subscribe(ReadyEvent, received, symbol_id=factories.SYMBOL_ID)

    assert emitter.subscription_count() == 0


async def test_an_unsubscribed_handler_stops_receiving(emitter: EventEmitter) -> None:
    received: Recorder[SpotEvent] = Recorder()
    emitter.subscribe(SpotEvent, received)

    removed = emitter.unsubscribe(SpotEvent, received)
    await emitter.emit(spot())

    assert removed is True
    assert received.count == 0


async def test_unsubscribing_leaves_other_handlers_subscribed(emitter: EventEmitter) -> None:
    leaving: Recorder[SpotEvent] = Recorder()
    staying: Recorder[SpotEvent] = Recorder()
    emitter.subscribe(SpotEvent, leaving)
    emitter.subscribe(SpotEvent, staying)

    emitter.unsubscribe(SpotEvent, leaving)
    await emitter.emit(spot())

    assert (leaving.count, staying.count) == (0, 1)


async def test_unsubscribing_a_handler_that_never_subscribed_reports_nothing_removed(
    emitter: EventEmitter,
) -> None:
    received: Recorder[SpotEvent] = Recorder()

    assert emitter.unsubscribe(SpotEvent, received) is False


async def test_unsubscribing_from_an_unrelated_type_does_not_remove_the_handler(
    emitter: EventEmitter,
) -> None:
    received: Recorder[Event] = Recorder()
    emitter.subscribe(SpotEvent, received)

    removed = emitter.unsubscribe(DepthEvent, received)
    await emitter.emit(spot())

    assert removed is False
    assert received.count == 1


async def test_clearing_one_type_leaves_the_others(emitter: EventEmitter) -> None:
    spots: Recorder[SpotEvent] = Recorder()
    ready: Recorder[ReadyEvent] = Recorder()
    emitter.subscribe(SpotEvent, spots)
    emitter.subscribe(SpotEvent, spots)
    emitter.subscribe(ReadyEvent, ready)

    removed = emitter.unsubscribe_all(SpotEvent)
    await emitter.emit(spot())

    assert removed == 2
    assert spots.count == 0
    assert emitter.subscription_count() == 1


async def test_clearing_everything_removes_every_subscription(emitter: EventEmitter) -> None:
    spots: Recorder[SpotEvent] = Recorder()
    ready: Recorder[ReadyEvent] = Recorder()
    emitter.subscribe(SpotEvent, spots)
    emitter.subscribe(ReadyEvent, ready)

    removed = emitter.unsubscribe_all()

    assert removed == 2
    assert emitter.subscription_count() == 0


async def test_the_same_handler_can_subscribe_twice_and_is_called_twice(emitter: EventEmitter) -> None:
    received: Recorder[SpotEvent] = Recorder()
    emitter.subscribe(SpotEvent, received, symbol_id=factories.SYMBOL_ID)
    emitter.subscribe(SpotEvent, received)

    await emitter.emit(spot())

    assert received.count == 2


async def test_unsubscribing_removes_only_one_of_two_identical_subscriptions(emitter: EventEmitter) -> None:
    received: Recorder[SpotEvent] = Recorder()
    emitter.subscribe(SpotEvent, received)
    emitter.subscribe(SpotEvent, received)

    emitter.unsubscribe(SpotEvent, received)
    await emitter.emit(spot())

    assert received.count == 1


async def test_a_failing_handler_does_not_stop_the_others(emitter: EventEmitter) -> None:
    failing: FailingRecorder[SpotEvent] = FailingRecorder()
    healthy: Recorder[SpotEvent] = Recorder()
    emitter.subscribe(SpotEvent, failing)
    emitter.subscribe(SpotEvent, healthy)

    await emitter.emit(spot())

    assert healthy.count == 1


async def test_a_failing_handler_does_not_break_the_emitter(emitter: EventEmitter) -> None:
    failing: FailingRecorder[SpotEvent] = FailingRecorder()
    emitter.subscribe(SpotEvent, failing)

    await emitter.emit(spot())
    await emitter.emit(spot())

    assert failing.count == 2


async def test_subscriptions_are_counted_per_type(emitter: EventEmitter) -> None:
    spots: Recorder[SpotEvent] = Recorder()
    ready: Recorder[ReadyEvent] = Recorder()
    emitter.subscribe(SpotEvent, spots)
    emitter.subscribe(SpotEvent, spots)
    emitter.subscribe(ReadyEvent, ready)

    assert emitter.subscription_count(SpotEvent) == 2
    assert emitter.subscription_count(ReadyEvent) == 1
    assert emitter.subscription_count() == 3


async def test_handlers_run_concurrently_rather_than_one_after_another(emitter: EventEmitter) -> None:
    """A handler that blocks must not hold up its siblings.

    Each handler announces its arrival, then waits for the other's. Concurrent
    dispatch lets them rendezvous and both finish; sequential dispatch would
    leave the first blocked forever on a handler that has not started yet, and
    fail_after would trip. This is what pins the concurrency guarantee: a
    regression to sequential delivery makes this test hang and fail.
    """
    first_arrived = anyio.Event()
    second_arrived = anyio.Event()
    finished: list[str] = []

    async def first(_: SpotEvent) -> None:
        first_arrived.set()
        await second_arrived.wait()
        finished.append("first")

    async def second(_: SpotEvent) -> None:
        second_arrived.set()
        await first_arrived.wait()
        finished.append("second")

    emitter.subscribe(SpotEvent, first)
    emitter.subscribe(SpotEvent, second)

    with anyio.fail_after(5):
        await emitter.emit(spot())

    assert set(finished) == {"first", "second"}


async def test_emit_returns_only_after_every_handler_has_finished(emitter: EventEmitter) -> None:
    """emit() awaits all handlers; it does not fire-and-forget onto a task group.

    The handler yields control at least once before recording completion, so a
    dispatch that returned without awaiting its tasks would let emit() return
    with `completed` still False.
    """
    completed = False

    async def handler(_: SpotEvent) -> None:
        nonlocal completed
        await anyio.sleep(0)
        completed = True

    emitter.subscribe(SpotEvent, handler)

    await emitter.emit(spot())

    assert completed is True
