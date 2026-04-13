"""Tests for ClientConfig."""

import pytest
from pydantic import ValidationError

from ctrader_api_client import ClientConfig


class TestClientConfigDefaults:
    """Test default configuration values."""

    def test_default_host(self):
        config = ClientConfig(client_id="id", client_secret="secret")
        assert config.host == "live.ctraderapi.com"

    def test_default_port(self):
        config = ClientConfig(client_id="id", client_secret="secret")
        assert config.port == 5035

    def test_default_use_ssl(self):
        config = ClientConfig(client_id="id", client_secret="secret")
        assert config.use_ssl is True

    def test_default_heartbeat_interval(self):
        config = ClientConfig(client_id="id", client_secret="secret")
        assert config.heartbeat_interval == 10.0

    def test_default_heartbeat_timeout(self):
        config = ClientConfig(client_id="id", client_secret="secret")
        assert config.heartbeat_timeout == 30.0

    def test_default_request_timeout(self):
        config = ClientConfig(client_id="id", client_secret="secret")
        assert config.request_timeout == 30.0

    def test_default_reconnect_attempts(self):
        config = ClientConfig(client_id="id", client_secret="secret")
        assert config.reconnect_attempts == 5

    def test_default_reconnect_min_wait(self):
        config = ClientConfig(client_id="id", client_secret="secret")
        assert config.reconnect_min_wait == 1.0

    def test_default_reconnect_max_wait(self):
        config = ClientConfig(client_id="id", client_secret="secret")
        assert config.reconnect_max_wait == 60.0


class TestClientConfigCustomValues:
    """Test custom configuration values."""

    def test_custom_host(self):
        config = ClientConfig(
            host="demo.ctraderapi.com",
            client_id="id",
            client_secret="secret",
        )
        assert config.host == "demo.ctraderapi.com"

    def test_custom_port(self):
        config = ClientConfig(
            port=5036,
            client_id="id",
            client_secret="secret",
        )
        assert config.port == 5036

    def test_custom_use_ssl_false(self):
        config = ClientConfig(
            use_ssl=False,
            client_id="id",
            client_secret="secret",
        )
        assert config.use_ssl is False

    def test_custom_heartbeat_settings(self):
        config = ClientConfig(
            heartbeat_interval=15.0,
            heartbeat_timeout=45.0,
            client_id="id",
            client_secret="secret",
        )
        assert config.heartbeat_interval == 15.0
        assert config.heartbeat_timeout == 45.0

    def test_custom_reconnect_settings(self):
        config = ClientConfig(
            reconnect_attempts=10,
            reconnect_min_wait=2.0,
            reconnect_max_wait=120.0,
            client_id="id",
            client_secret="secret",
        )
        assert config.reconnect_attempts == 10
        assert config.reconnect_min_wait == 2.0
        assert config.reconnect_max_wait == 120.0


class TestClientConfigValidation:
    """Test configuration validation."""

    def test_requires_client_id(self):
        with pytest.raises(ValidationError):
            ClientConfig(client_secret="secret")  # ty: ignore[missing-argument]

    def test_requires_client_secret(self):
        with pytest.raises(ValidationError):
            ClientConfig(client_id="id")  # ty: ignore[missing-argument]

    def test_heartbeat_interval_must_be_positive(self):
        with pytest.raises(ValidationError):
            ClientConfig(
                client_id="id",
                client_secret="secret",
                heartbeat_interval=0,
            )

    def test_heartbeat_timeout_must_be_positive(self):
        with pytest.raises(ValidationError):
            ClientConfig(
                client_id="id",
                client_secret="secret",
                heartbeat_timeout=0,
            )

    def test_request_timeout_must_be_positive(self):
        with pytest.raises(ValidationError):
            ClientConfig(
                client_id="id",
                client_secret="secret",
                request_timeout=-1,
            )

    def test_reconnect_attempts_can_be_zero(self):
        config = ClientConfig(
            client_id="id",
            client_secret="secret",
            reconnect_attempts=0,
        )
        assert config.reconnect_attempts == 0

    def test_reconnect_attempts_cannot_be_negative(self):
        with pytest.raises(ValidationError):
            ClientConfig(
                client_id="id",
                client_secret="secret",
                reconnect_attempts=-1,
            )


class TestClientConfigImmutability:
    """Test that config is immutable."""

    def test_config_is_frozen(self):
        config = ClientConfig(client_id="id", client_secret="secret")
        with pytest.raises(ValidationError):
            config.host = "other.host.com"  # type: ignore[misc]
