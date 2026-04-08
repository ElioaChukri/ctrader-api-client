"""Tests for AccountCredentials."""

from __future__ import annotations

import time

from ctrader_api_client.auth.credentials import AccountCredentials


class TestAccountCredentialsInit:
    """Tests for AccountCredentials initialization."""

    def test_stores_all_fields(self) -> None:
        creds = AccountCredentials(
            account_id=12345,
            access_token="access_token_123",
            refresh_token="refresh_token_456",
            expires_at=1700000000.0,
        )

        assert creds.account_id == 12345
        assert creds.access_token == "access_token_123"
        assert creds.refresh_token == "refresh_token_456"
        assert creds.expires_at == 1700000000.0


class TestExpiresSoon:
    """Tests for AccountCredentials.expires_soon()."""

    def test_returns_true_when_within_buffer(self) -> None:
        # Token expires in 100 seconds
        creds = AccountCredentials(
            account_id=1,
            access_token="token",
            refresh_token="refresh",
            expires_at=time.time() + 100,
        )

        # Default buffer is 300 seconds, so should be "expiring soon"
        assert creds.expires_soon() is True

    def test_returns_false_when_outside_buffer(self) -> None:
        # Token expires in 1 hour
        creds = AccountCredentials(
            account_id=1,
            access_token="token",
            refresh_token="refresh",
            expires_at=time.time() + 3600,
        )

        # Default buffer is 300 seconds, so should not be "expiring soon"
        assert creds.expires_soon() is False

    def test_custom_buffer(self) -> None:
        # Token expires in 100 seconds
        creds = AccountCredentials(
            account_id=1,
            access_token="token",
            refresh_token="refresh",
            expires_at=time.time() + 100,
        )

        # With 50 second buffer, should not be expiring soon
        assert creds.expires_soon(buffer_seconds=50) is False

        # With 200 second buffer, should be expiring soon
        assert creds.expires_soon(buffer_seconds=200) is True

    def test_returns_true_when_already_expired(self) -> None:
        creds = AccountCredentials(
            account_id=1,
            access_token="token",
            refresh_token="refresh",
            expires_at=time.time() - 100,  # Expired 100 seconds ago
        )

        assert creds.expires_soon() is True


class TestIsExpired:
    """Tests for AccountCredentials.is_expired()."""

    def test_returns_true_when_expired(self) -> None:
        creds = AccountCredentials(
            account_id=1,
            access_token="token",
            refresh_token="refresh",
            expires_at=time.time() - 100,
        )

        assert creds.is_expired() is True

    def test_returns_false_when_not_expired(self) -> None:
        creds = AccountCredentials(
            account_id=1,
            access_token="token",
            refresh_token="refresh",
            expires_at=time.time() + 3600,
        )

        assert creds.is_expired() is False


class TestTimeUntilExpiry:
    """Tests for AccountCredentials.time_until_expiry()."""

    def test_returns_positive_for_valid_token(self) -> None:
        expires_in = 3600
        creds = AccountCredentials(
            account_id=1,
            access_token="token",
            refresh_token="refresh",
            expires_at=time.time() + expires_in,
        )

        remaining = creds.time_until_expiry()
        # Should be close to expires_in (within 1 second tolerance)
        assert expires_in - 1 <= remaining <= expires_in + 1

    def test_returns_negative_for_expired_token(self) -> None:
        creds = AccountCredentials(
            account_id=1,
            access_token="token",
            refresh_token="refresh",
            expires_at=time.time() - 100,
        )

        remaining = creds.time_until_expiry()
        assert remaining < 0


class TestWithRefreshedTokens:
    """Tests for AccountCredentials.with_refreshed_tokens()."""

    def test_creates_new_instance(self) -> None:
        original = AccountCredentials(
            account_id=12345,
            access_token="old_access",
            refresh_token="old_refresh",
            expires_at=time.time() + 100,
        )

        refreshed = original.with_refreshed_tokens(
            access_token="new_access",
            refresh_token="new_refresh",
            expires_in=7200,
        )

        # Original unchanged
        assert original.access_token == "old_access"
        assert original.refresh_token == "old_refresh"

        # New instance has updated tokens
        assert refreshed is not original
        assert refreshed.account_id == 12345  # Preserved
        assert refreshed.access_token == "new_access"
        assert refreshed.refresh_token == "new_refresh"

    def test_calculates_new_expiry_from_expires_in(self) -> None:
        original = AccountCredentials(
            account_id=1,
            access_token="old",
            refresh_token="old",
            expires_at=0,
        )

        expires_in = 3600
        before = time.time()
        refreshed = original.with_refreshed_tokens(
            access_token="new",
            refresh_token="new",
            expires_in=expires_in,
        )
        after = time.time()

        # New expiry should be current time + expires_in
        assert before + expires_in <= refreshed.expires_at <= after + expires_in
