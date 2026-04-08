"""Connection layer for cTrader API.

This module provides TCP/SSL transport, message protocol handling,
and heartbeat management for maintaining connections to cTrader servers.
"""

from .heartbeat import HeartbeatManager
from .protocol import Protocol
from .transport import Transport


__all__ = [
    "HeartbeatManager",
    "Protocol",
    "Transport",
]
