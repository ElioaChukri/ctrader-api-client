"""Fixtures for the auth behaviour tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import pytest

from ctrader_api_client.auth import AuthManager, ReauthPolicy, RefreshPolicy

from ...harness import ManualClock, StubProtocol


@pytest.fixture
async def make_auth(
    protocol: StubProtocol,
    clock: ManualClock,
) -> AsyncIterator[Callable[..., AuthManager]]:
    """Build auth managers with their background loops running.

    Retry waits are collapsed because they are driven by tenacity rather than
    the injected clock; the check interval stays large so refreshes only happen
    when a test advances time.
    """
    managers: list[AuthManager] = []

    def factory(check_interval: float = 60.0, **overrides: object) -> AuthManager:
        settings: dict[str, object] = {
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "refresh_policy": RefreshPolicy(
                check_interval=check_interval,
                retry_min_wait=0.001,
                retry_max_wait=0.01,
            ),
            "reauth_policy": ReauthPolicy(min_wait=0.001, max_wait=0.01),
        }
        settings.update(overrides)
        manager = AuthManager(protocol=protocol, clock=clock, **settings)  # type: ignore[arg-type]
        managers.append(manager)
        return manager

    yield factory

    for manager in managers:
        await manager.stop()


@pytest.fixture
def auth(make_auth: Callable[..., AuthManager]) -> AuthManager:
    """An auth manager with default settings."""
    return make_auth()
