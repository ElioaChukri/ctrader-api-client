"""The producer side of the event bus."""

from __future__ import annotations

from typing import Protocol as TypingProtocol

from .types import Event


class EventPublisher(TypingProtocol):
    """Somewhere to publish an event.

    Injected into components that report what happened, so they depend on the
    act of publishing rather than on the whole subscription machinery.
    """

    async def emit(self, event: Event) -> None:
        """Deliver the event to everyone subscribed to its type."""
        ...
