from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ..connection import Protocol


class BaseAPI:
    """Shared construction and timeout handling for API namespaces."""

    def __init__(self, protocol: Protocol, default_timeout: float = 30.0) -> None:
        """Initialize the API namespace.

        Args:
            protocol: The protocol instance for sending requests.
            default_timeout: Default request timeout in seconds.
        """
        self._protocol = protocol
        self._default_timeout = default_timeout

    def _timeout(self, timeout: float | None) -> float:
        """Resolve a per-call timeout against the configured default."""
        return timeout or self._default_timeout
