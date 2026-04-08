"""Connection layer for cTrader API.

This module provides TCP/SSL transport, message protocol handling,
and heartbeat management for maintaining connections to cTrader servers.
"""

from ctrader_api_client.connection.heartbeat import HeartbeatManager
from ctrader_api_client.connection.protocol import Protocol
from ctrader_api_client.connection.transport import Transport


__all__ = [
    "HeartbeatManager",
    "Protocol",
    "Transport",
]
