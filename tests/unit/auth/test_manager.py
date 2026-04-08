"""Tests for AuthManager."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import anyio
import pytest

from ctrader_api_client._internal.proto import (
    ProtoOAAccountAuthRes,
    ProtoOAApplicationAuthRes,
    ProtoOARefreshTokenReq,
    ProtoOARefreshTokenRes,
)
from ctrader_api_client.auth.credentials import AccountCredentials
from ctrader_api_client.auth.manager import AuthManager
from ctrader_api_client.connection.protocol import Protocol
from ctrader_api_client.exceptions import APIError, TokenRefreshError


@pytest.fixture
def mock_protocol() -> MagicMock:
    """Create a mock protocol."""
    protocol = MagicMock(spec=Protocol)
    protocol.send_request = AsyncMock()
    return protocol


@pytest.fixture
def sample_credentials() -> AccountCredentials:
    """Create sample account credentials."""
    return AccountCredentials(
        account_id=12345,
        access_token="access_token_123",
        refresh_token="refresh_token_456",
        expires_at=time.time() + 3600,  # Expires in 1 hour
    )


class TestAuthManagerInit:
    """Tests for AuthManager initialization."""

    def test_stores_protocol_and_credentials(self, mock_protocol: MagicMock) -> None:
        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test_client",
            client_secret="test_secret",
        )

        assert auth._protocol is mock_protocol
        assert auth._client_id == "test_client"
        assert auth._client_secret == "test_secret"

    def test_default_settings(self, mock_protocol: MagicMock) -> None:
        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
        )

        assert auth._refresh_buffer == 300.0
        assert auth._check_interval == 60.0
        assert auth._retry_attempts == 3

    def test_custom_settings(self, mock_protocol: MagicMock) -> None:
        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
            refresh_buffer_seconds=600,
            refresh_check_interval=120,
            refresh_retry_attempts=5,
        )

        assert auth._refresh_buffer == 600
        assert auth._check_interval == 120
        assert auth._retry_attempts == 5

    def test_not_authenticated_initially(self, mock_protocol: MagicMock) -> None:
        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
        )

        assert auth.is_app_authenticated is False
        assert auth.authenticated_accounts == []


class TestAuthenticateApp:
    """Tests for AuthManager.authenticate_app()."""

    @pytest.mark.anyio
    async def test_sends_app_auth_request(self, mock_protocol: MagicMock) -> None:
        mock_protocol.send_request.return_value = ProtoOAApplicationAuthRes()

        auth = AuthManager(
            protocol=mock_protocol,
            client_id="my_client_id",
            client_secret="my_secret",
        )

        await auth.authenticate_app()

        mock_protocol.send_request.assert_called_once()
        request = mock_protocol.send_request.call_args[0][0]
        assert request.client_id == "my_client_id"
        assert request.client_secret == "my_secret"

    @pytest.mark.anyio
    async def test_sets_authenticated_flag(self, mock_protocol: MagicMock) -> None:
        mock_protocol.send_request.return_value = ProtoOAApplicationAuthRes()

        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
        )

        assert auth.is_app_authenticated is False
        await auth.authenticate_app()
        assert auth.is_app_authenticated is True

    @pytest.mark.anyio
    async def test_returns_response(self, mock_protocol: MagicMock) -> None:
        expected_response = ProtoOAApplicationAuthRes()
        mock_protocol.send_request.return_value = expected_response

        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
        )

        response = await auth.authenticate_app()
        assert response is expected_response


class TestAuthenticateAccount:
    """Tests for AuthManager.authenticate_account()."""

    @pytest.mark.anyio
    async def test_sends_account_auth_request(
        self,
        mock_protocol: MagicMock,
        sample_credentials: AccountCredentials,
    ) -> None:
        mock_protocol.send_request.return_value = ProtoOAAccountAuthRes(
            ctid_trader_account_id=sample_credentials.account_id
        )

        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
        )

        await auth.authenticate_account(sample_credentials)

        mock_protocol.send_request.assert_called_once()
        request = mock_protocol.send_request.call_args[0][0]
        assert request.ctid_trader_account_id == sample_credentials.account_id
        assert request.access_token == sample_credentials.access_token

    @pytest.mark.anyio
    async def test_stores_credentials(
        self,
        mock_protocol: MagicMock,
        sample_credentials: AccountCredentials,
    ) -> None:
        mock_protocol.send_request.return_value = ProtoOAAccountAuthRes(
            ctid_trader_account_id=sample_credentials.account_id
        )

        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
        )

        await auth.authenticate_account(sample_credentials)

        assert sample_credentials.account_id in auth.authenticated_accounts
        assert auth.get_credentials(sample_credentials.account_id) is sample_credentials

    @pytest.mark.anyio
    async def test_multiple_accounts(self, mock_protocol: MagicMock) -> None:
        mock_protocol.send_request.return_value = ProtoOAAccountAuthRes()

        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
        )

        creds1 = AccountCredentials(1, "token1", "refresh1", time.time() + 3600)
        creds2 = AccountCredentials(2, "token2", "refresh2", time.time() + 3600)

        await auth.authenticate_account(creds1)
        await auth.authenticate_account(creds2)

        assert set(auth.authenticated_accounts) == {1, 2}


class TestRemoveAccount:
    """Tests for AuthManager.remove_account()."""

    @pytest.mark.anyio
    async def test_removes_existing_account(
        self,
        mock_protocol: MagicMock,
        sample_credentials: AccountCredentials,
    ) -> None:
        mock_protocol.send_request.return_value = ProtoOAAccountAuthRes()

        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
        )

        await auth.authenticate_account(sample_credentials)
        result = auth.remove_account(sample_credentials.account_id)

        assert result is True
        assert sample_credentials.account_id not in auth.authenticated_accounts

    def test_returns_false_for_nonexistent_account(self, mock_protocol: MagicMock) -> None:
        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
        )

        result = auth.remove_account(99999)
        assert result is False


class TestStartStop:
    """Tests for AuthManager.start() and stop()."""

    @pytest.mark.anyio
    async def test_start_sets_running(self, mock_protocol: MagicMock) -> None:
        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
            refresh_check_interval=0.01,
        )

        await auth.start()

        try:
            assert auth._running is True
            assert auth._task_group is not None
        finally:
            await auth.stop()

    @pytest.mark.anyio
    async def test_stop_clears_running(self, mock_protocol: MagicMock) -> None:
        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
            refresh_check_interval=0.01,
        )

        await auth.start()
        await auth.stop()

        assert auth._running is False
        assert auth._task_group is None

    @pytest.mark.anyio
    async def test_start_is_idempotent(self, mock_protocol: MagicMock) -> None:
        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
            refresh_check_interval=0.01,
        )

        await auth.start()
        task_group_1 = auth._task_group

        await auth.start()  # Second call
        task_group_2 = auth._task_group

        try:
            assert task_group_1 is task_group_2
        finally:
            await auth.stop()


class TestTokenRefresh:
    """Tests for token refresh functionality."""

    @pytest.mark.anyio
    async def test_refresh_updates_credentials(self, mock_protocol: MagicMock) -> None:
        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
        )

        # Store initial credentials
        old_creds = AccountCredentials(
            account_id=12345,
            access_token="old_token",
            refresh_token="old_refresh",
            expires_at=time.time() + 100,
        )
        auth._accounts[old_creds.account_id] = old_creds

        # Mock refresh response
        mock_protocol.send_request.side_effect = [
            ProtoOARefreshTokenRes(
                access_token="new_token",
                refresh_token="new_refresh",
                expires_in=7200,
            ),
            ProtoOAAccountAuthRes(ctid_trader_account_id=12345),
        ]

        await auth._refresh_account(12345)

        new_creds = auth.get_credentials(12345)
        assert new_creds is not None
        assert new_creds.access_token == "new_token"
        assert new_creds.refresh_token == "new_refresh"

    @pytest.mark.anyio
    async def test_refresh_calls_callback(self, mock_protocol: MagicMock) -> None:
        callback_called_with: list[AccountCredentials] = []

        async def on_refresh(creds: AccountCredentials) -> None:
            callback_called_with.append(creds)

        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
            on_tokens_refreshed=on_refresh,
        )

        old_creds = AccountCredentials(
            account_id=12345,
            access_token="old",
            refresh_token="old",
            expires_at=time.time() + 100,
        )
        auth._accounts[old_creds.account_id] = old_creds

        mock_protocol.send_request.side_effect = [
            ProtoOARefreshTokenRes(
                access_token="new",
                refresh_token="new",
                expires_in=3600,
            ),
            ProtoOAAccountAuthRes(ctid_trader_account_id=12345),
        ]

        await auth._refresh_account(12345)

        assert len(callback_called_with) == 1
        assert callback_called_with[0].access_token == "new"

    @pytest.mark.anyio
    async def test_refresh_retries_on_failure(self, mock_protocol: MagicMock) -> None:
        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
            refresh_retry_attempts=3,
            refresh_retry_min_wait=0.01,
            refresh_retry_max_wait=0.02,
        )

        creds = AccountCredentials(
            account_id=1,
            access_token="token",
            refresh_token="refresh",
            expires_at=time.time() + 100,
        )
        auth._accounts[1] = creds

        # Fail twice, then succeed
        mock_protocol.send_request.side_effect = [
            APIError("TEMPORARY_ERROR"),
            APIError("TEMPORARY_ERROR"),
            ProtoOARefreshTokenRes(
                access_token="new",
                refresh_token="new",
                expires_in=3600,
            ),
            ProtoOAAccountAuthRes(ctid_trader_account_id=1),
        ]

        await auth._refresh_account(1)

        # Should have called send_request 4 times (2 failures + 1 success + 1 reauth)
        assert mock_protocol.send_request.call_count == 4

    @pytest.mark.anyio
    async def test_refresh_raises_after_all_retries(self, mock_protocol: MagicMock) -> None:
        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
            refresh_retry_attempts=2,
            refresh_retry_min_wait=0.01,
            refresh_retry_max_wait=0.02,
        )

        creds = AccountCredentials(
            account_id=1,
            access_token="token",
            refresh_token="refresh",
            expires_at=time.time() + 100,
        )
        auth._accounts[1] = creds

        # Always fail
        mock_protocol.send_request.side_effect = APIError("PERMANENT_ERROR")

        with pytest.raises(TokenRefreshError) as exc_info:
            await auth._refresh_account(1)

        assert exc_info.value.ctid_trader_account_id == 1


class TestRefreshLoop:
    """Tests for the automatic refresh loop."""

    @pytest.mark.anyio
    async def test_refresh_loop_triggers_for_expiring_token(
        self,
        mock_protocol: MagicMock,
    ) -> None:
        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
            refresh_buffer_seconds=500,  # Consider "expiring soon" within 500s
            refresh_check_interval=0.02,
        )

        # Token expires in 100 seconds (within buffer)
        expiring_creds = AccountCredentials(
            account_id=1,
            access_token="old",
            refresh_token="refresh",
            expires_at=time.time() + 100,
        )
        auth._accounts[1] = expiring_creds

        mock_protocol.send_request.side_effect = [
            ProtoOARefreshTokenRes(
                access_token="new",
                refresh_token="new",
                expires_in=3600,
            ),
            ProtoOAAccountAuthRes(ctid_trader_account_id=1),
        ]

        await auth.start()

        # Wait for refresh loop to run
        await anyio.sleep(0.05)

        await auth.stop()

        # Verify refresh request was sent
        calls = mock_protocol.send_request.call_args_list
        refresh_calls = [call for call in calls if isinstance(call[0][0], ProtoOARefreshTokenReq)]
        assert len(refresh_calls) >= 1

        # Verify credentials were updated
        updated_creds = auth.get_credentials(1)
        assert updated_creds is not None
        assert updated_creds.access_token == "new"
        assert updated_creds.refresh_token == "new"

    @pytest.mark.anyio
    async def test_refresh_loop_does_not_trigger_for_valid_token(
        self,
        mock_protocol: MagicMock,
    ) -> None:
        auth = AuthManager(
            protocol=mock_protocol,
            client_id="test",
            client_secret="test",
            refresh_buffer_seconds=60,
            refresh_check_interval=0.02,
        )

        # Token expires in 1 hour (outside buffer)
        valid_creds = AccountCredentials(
            account_id=1,
            access_token="token",
            refresh_token="refresh",
            expires_at=time.time() + 3600,
        )
        auth._accounts[1] = valid_creds

        await auth.start()

        # Wait for a few check cycles
        await anyio.sleep(0.05)

        await auth.stop()

        # Should not have sent any requests
        mock_protocol.send_request.assert_not_called()

        # Credentials should remain unchanged
        unchanged_creds = auth.get_credentials(1)
        assert unchanged_creds is not None
        assert unchanged_creds.access_token == "token"
        assert unchanged_creds.refresh_token == "refresh"
