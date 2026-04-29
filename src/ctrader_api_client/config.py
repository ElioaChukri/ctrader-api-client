from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ClientConfig(BaseModel):
    """Configuration for CTraderClient.

    Attributes:
        host: cTrader API server hostname.
        port: cTrader API server port.
        use_ssl: Whether to use SSL/TLS encryption.
        client_id: OAuth application client ID.
        client_secret: OAuth application client secret.
        heartbeat_interval: Seconds between heartbeat sends.
        heartbeat_timeout: Seconds without server-initiated messages before disconnect. Set to 0 to disable.
        request_timeout: Default timeout for API requests in seconds.
        reconnect_attempts: Max reconnection attempts (0 to disable).
        reconnect_min_wait: Initial wait between reconnection attempts.
        reconnect_max_wait: Maximum wait between reconnection attempts.

    Example:
        ```python
        config = ClientConfig(client_id="your_client_id", client_secret="your_client_secret")

        # For demo server
        demo_config = ClientConfig(
            host="demo.ctraderapi.com",
            client_id="your_client_id",
            client_secret="your_client_secret",
        )
        ```
    """

    # Connection settings
    host: str = "live.ctraderapi.com"
    port: int = 5035
    use_ssl: bool = True

    # OAuth credentials
    client_id: str
    client_secret: str

    # Heartbeat settings
    heartbeat_interval: float = Field(default=10.0, gt=0)
    heartbeat_timeout: float = Field(default=60.0, ge=0)

    # Request settings
    request_timeout: float = Field(default=30.0, gt=0)

    # Reconnection settings
    reconnect_attempts: int = Field(default=5, ge=0)
    reconnect_min_wait: float = Field(default=1.0, gt=0)
    reconnect_max_wait: float = Field(default=60.0, gt=0)

    model_config = ConfigDict(frozen=True)
