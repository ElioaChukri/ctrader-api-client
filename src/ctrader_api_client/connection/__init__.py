"""Connection layer for cTrader API.

This module provides TCP/SSL transport, message protocol handling,
and heartbeat management for maintaining connections to cTrader servers.
"""

from .heartbeat import HeartbeatManager
from .listener import ConnectionListener
from .protocol import Protocol
from .supervisor import ConnectionSupervisor
from .transport import Transport


__all__ = [
    "ConnectionListener",
    "ConnectionSupervisor",
    "HeartbeatManager",
    "Protocol",
    "Transport",
]
