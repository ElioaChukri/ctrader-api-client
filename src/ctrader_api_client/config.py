from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .auth import ReauthPolicy, RefreshPolicy


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
        connect_timeout: Seconds allowed for the TCP connection and TLS
            handshake together, after which the attempt is failed and retried.
        reconnect_attempts: Max reconnection attempts. None (the default)
            retries for as long as the client is open. 0 disables reconnection.
            A finite budget that runs out abandons the connection and raises
            CTraderReconnectAbandonedError out of the `async with` block.
        reconnect_min_wait: Initial wait between reconnection attempts.
        reconnect_max_wait: Maximum wait between reconnection attempts.
        refresh_policy: When to refresh access tokens and how hard to try.
        reauth_policy: Backoff for re-establishing sessions the server dropped.

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
    connect_timeout: float = Field(default=30.0, gt=0)

    # Reconnection settings
    reconnect_attempts: int | None = Field(default=None, ge=0)
    reconnect_min_wait: float = Field(default=1.0, gt=0)
    reconnect_max_wait: float = Field(default=60.0, gt=0)

    # Authentication settings
    refresh_policy: RefreshPolicy = RefreshPolicy()
    reauth_policy: ReauthPolicy = ReauthPolicy()

    model_config = ConfigDict(frozen=True)
