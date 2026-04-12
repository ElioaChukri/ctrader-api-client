from __future__ import annotations

from typing import TYPE_CHECKING

from ._internal.proto import ProtoOAErrorCode


if TYPE_CHECKING:
    from ._internal.proto import ProtoOAErrorRes


class CTraderError(Exception):
    """Base exception for all cTrader API errors."""


# =============================================================================
# Connection Errors
# =============================================================================


class CTraderConnectionError(CTraderError):
    """Base exception for connection-related errors."""


class CTraderConnectionFailedError(CTraderConnectionError):
    """Failed to establish connection to the server."""

    def __init__(self, host: str, port: int, cause: Exception | None = None) -> None:
        self.host = host
        self.port = port
        self.cause = cause
        message = f"Failed to connect to {host}:{port}"
        if cause:
            message += f": {cause}"
        super().__init__(message)


class CTraderConnectionClosedError(CTraderConnectionError):
    """Connection was closed unexpectedly."""

    def __init__(self, reason: str | None = None, was_clean: bool = False) -> None:
        self.reason = reason
        self.was_clean = was_clean
        message = "Connection closed"
        if was_clean:
            message += " cleanly"
        if reason:
            message += f": {reason}"
        super().__init__(message)


class CTraderConnectionTimeoutError(CTraderConnectionError):
    """Connection operation timed out."""

    def __init__(self, timeout_seconds: float, operation: str = "operation") -> None:
        self.timeout_seconds = timeout_seconds
        self.operation = operation
        super().__init__(f"{operation} timed out after {timeout_seconds}s")


# =============================================================================
# Authentication Errors
# =============================================================================


class AuthenticationError(CTraderError):
    """Base exception for authentication-related errors."""


class ApplicationAuthError(AuthenticationError):
    """Application authentication failed."""

    def __init__(self, error_code: str, description: str | None = None) -> None:
        self.error_code = error_code
        self.description = description
        message = f"Application authentication failed: {error_code}"
        if description:
            message += f" - {description}"
        super().__init__(message)


class AccountAuthError(AuthenticationError):
    """Account authentication failed."""

    def __init__(
        self,
        error_code: str,
        description: str | None = None,
        ctid_trader_account_id: int | None = None,
    ) -> None:
        self.error_code = error_code
        self.description = description
        self.ctid_trader_account_id = ctid_trader_account_id
        message = f"Account authentication failed: {error_code}"
        if ctid_trader_account_id:
            message += f" (account: {ctid_trader_account_id})"
        if description:
            message += f" - {description}"
        super().__init__(message)


class TokenExpiredError(AuthenticationError):
    """Access token has expired."""

    def __init__(self, ctid_trader_account_id: int | None = None) -> None:
        self.ctid_trader_account_id = ctid_trader_account_id
        message = "Access token has expired"
        if ctid_trader_account_id:
            message += f" for account {ctid_trader_account_id}"
        super().__init__(message)


class TokenRefreshError(AuthenticationError):
    """Failed to refresh access token."""

    def __init__(
        self,
        ctid_trader_account_id: int | None = None,
        cause: Exception | None = None,
    ) -> None:
        self.ctid_trader_account_id = ctid_trader_account_id
        self.cause = cause
        message = "Failed to refresh access token"
        if ctid_trader_account_id:
            message += f" for account {ctid_trader_account_id}"
        if cause:
            message += f": {cause}"
        super().__init__(message)


class AccountNotFoundError(AuthenticationError):
    """No account found matching the given criteria."""

    def __init__(
        self,
        trader_login: int,
        available_logins: list[int] | None = None,
    ) -> None:
        self.trader_login = trader_login
        self.available_logins = available_logins
        message = f"No account found with trader login {trader_login}"
        if available_logins:
            message += f". Available logins: {available_logins}"
        super().__init__(message)


# =============================================================================
# API Errors
# =============================================================================


class APIError(CTraderError):
    """Error response from the cTrader API."""

    def __init__(
        self,
        error_code: str,
        description: str | None = None,
        ctid_trader_account_id: int | None = None,
        maintenance_end_timestamp: int | None = None,
        retry_after: int | None = None,
    ) -> None:
        self.error_code = error_code
        self.description = description
        self.ctid_trader_account_id = ctid_trader_account_id
        self.maintenance_end_timestamp = maintenance_end_timestamp
        self.retry_after = retry_after

        message = f"API error: {error_code}"
        if ctid_trader_account_id:
            message += f" (account: {ctid_trader_account_id})"
        if description:
            message += f" - {description}"
        super().__init__(message)

    @classmethod
    def from_proto(cls, error_res: ProtoOAErrorRes) -> APIError:
        """Create an APIError from a ProtoOAErrorRes message."""
        return cls(
            error_code=error_res.error_code,
            description=error_res.description or None,
            ctid_trader_account_id=error_res.ctid_trader_account_id or None,
            maintenance_end_timestamp=error_res.maintenance_end_timestamp or None,
            retry_after=error_res.retry_after or None,
        )

    def is_rate_limited(self) -> bool:
        """Check if this error indicates rate limiting."""
        return self.error_code == ProtoOAErrorCode.REQUEST_FREQUENCY_EXCEEDED.name or self.retry_after is not None

    def is_maintenance(self) -> bool:
        """Check if this error indicates server maintenance."""
        return (
            self.error_code == ProtoOAErrorCode.SERVER_IS_UNDER_MAINTENANCE.name
            or self.maintenance_end_timestamp is not None
        )


# =============================================================================
# Protocol Errors
# =============================================================================


class ProtocolError(CTraderError):
    """Base exception for protocol-level errors."""


class FramingError(ProtocolError):
    """Error in wire protocol framing."""

    def __init__(self, expected_bytes: int, received_bytes: int) -> None:
        self.expected_bytes = expected_bytes
        self.received_bytes = received_bytes
        super().__init__(f"Framing error: expected {expected_bytes} bytes, received {received_bytes}")


class DeserializationError(ProtocolError):
    """Failed to deserialize a protobuf message."""

    def __init__(self, payload_type: int, raw_data: bytes) -> None:
        self.payload_type = payload_type
        self.raw_data = raw_data
        super().__init__(f"Failed to deserialize message with payload type {payload_type} ({len(raw_data)} bytes)")


class UnknownPayloadTypeError(ProtocolError):
    """Received a message with an unknown payload type."""

    def __init__(self, payload_type: int) -> None:
        self.payload_type = payload_type
        super().__init__(f"Unknown payload type: {payload_type}")
