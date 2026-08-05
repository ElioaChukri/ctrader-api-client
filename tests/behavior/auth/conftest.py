"""Fixtures for the auth behaviour tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from ctrader_api_client.auth import (
    AuthManager,
    ReauthPolicy,
    RefreshPolicy,
    SessionRecovery,
    SessionStore,
    TokenRefresher,
)

from ...harness import ManualClock, RecordingPublisher, StubProtocol


@dataclass(frozen=True, slots=True)
class Monitors:
    """The two background monitors, already running against the shared store."""

    refresher: TokenRefresher
    recovery: SessionRecovery


@pytest.fixture
def publisher() -> RecordingPublisher:
    """Records every event the components under test publish."""
    return RecordingPublisher()


@pytest.fixture
def sessions() -> SessionStore:
    """The accounts and session state the auth components share."""
    return SessionStore()


@pytest.fixture
def make_auth(
    protocol: StubProtocol,
    publisher: RecordingPublisher,
    sessions: SessionStore,
) -> Callable[..., AuthManager]:
    """Build auth managers over the shared session store."""

    def factory(**overrides: object) -> AuthManager:
        settings: dict[str, object] = {
            "publisher": publisher,
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "store": sessions,
        }
        settings.update(overrides)
        return AuthManager(protocol=protocol, **settings)  # type: ignore[arg-type]

    return factory


@pytest.fixture
def auth(make_auth: Callable[..., AuthManager]) -> AuthManager:
    """An auth manager with default settings."""
    return make_auth()


@pytest.fixture
def make_monitors(
    protocol: StubProtocol,
    clock: ManualClock,
    publisher: RecordingPublisher,
    sessions: SessionStore,
    auth: AuthManager,
    serving: Callable[[TokenRefresher | SessionRecovery], None],
) -> Callable[..., Monitors]:
    """Build the refresh and recovery monitors with their loops already running.

    Retry waits are collapsed because they are driven by tenacity rather than
    the injected clock; the check interval stays large so refreshes only happen
    when a test advances time.
    """

    def factory(
        check_interval: float = 60.0,
        reauth_policy: ReauthPolicy | None = None,
        **overrides: object,
    ) -> Monitors:
        refresher = TokenRefresher(
            protocol=protocol,
            store=sessions,
            authenticator=auth,
            publisher=publisher,
            policy=RefreshPolicy(
                check_interval=check_interval,
                retry_min_wait=0.001,
                retry_max_wait=0.01,
            ),
            clock=clock,
            **overrides,  # type: ignore[arg-type]
        )
        recovery = SessionRecovery(
            store=sessions,
            authenticator=auth,
            publisher=publisher,
            policy=reauth_policy if reauth_policy is not None else ReauthPolicy(min_wait=0.001, max_wait=0.01),
            clock=clock,
        )
        serving(refresher)
        serving(recovery)
        return Monitors(refresher=refresher, recovery=recovery)

    return factory


@pytest.fixture
async def monitors(make_monitors: Callable[..., Monitors]) -> Monitors:
    """Both monitors with default settings."""
    return make_monitors()
