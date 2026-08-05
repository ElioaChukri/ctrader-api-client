"""The port the connection layer reports link transitions through."""

from __future__ import annotations

from typing import Protocol as TypingProtocol


class ConnectionListener(TypingProtocol):
    """Whatever holds state that only exists while the link is up."""

    async def on_connection_lost(self) -> None:
        """React to a dropped link, before reconnection is attempted."""
        ...

    async def on_connection_restored(self) -> None:
        """Re-establish that state on the new link, before queued work resumes."""
        ...
