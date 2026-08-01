"""Retry and timing policies for authentication.

Grouping these knobs into objects keeps them together as they travel from
:class:`~ctrader_api_client.config.ClientConfig` down into the auth manager,
instead of spreading eight loose floats across every layer in between.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RefreshPolicy:
    """When to refresh an access token, and how hard to try.

    Attributes:
        buffer_seconds: Refresh a token this many seconds before it expires.
        check_interval: How often to look for tokens that are expiring.
        retry_attempts: How many times a single refresh is attempted before it
            is reported as failed. The credentials are kept either way, so the
            next check interval tries again.
        retry_min_wait: Initial wait between refresh attempts.
        retry_max_wait: Cap on the exponential backoff between attempts.
    """

    buffer_seconds: float = 300.0
    check_interval: float = 60.0
    retry_attempts: int = 3
    retry_min_wait: float = 1.0
    retry_max_wait: float = 30.0


@dataclass(frozen=True, slots=True)
class ReauthPolicy:
    """How hard to try to re-establish a session the server dropped.

    Recovery is retried indefinitely, so there is no attempt limit — only the
    backoff between attempts, which is tracked per account.

    Attributes:
        min_wait: Wait before the first retry, and after any success.
        max_wait: Cap on the exponential backoff between attempts.
    """

    min_wait: float = 1.0
    max_wait: float = 60.0
