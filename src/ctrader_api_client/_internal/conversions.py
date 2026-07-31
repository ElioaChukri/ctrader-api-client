"""Conversions between wire representations and Python types."""

from __future__ import annotations

from datetime import UTC, datetime


# The scale the server uses for monetary amounts when it does not say otherwise.
# money_digits is a plain proto3 scalar, so a message that omits it parses as 0,
# which would scale by 1 and overstate every amount by two orders of magnitude.
DEFAULT_MONEY_DIGITS = 2


def money_divisor(money_digits: int) -> int:
    """Return the divisor that turns a scaled money integer into its real value.

    Monetary amounts arrive as integers scaled by ``10 ** money_digits``. A
    ``money_digits`` of 0 is read as absent rather than as "no scaling", because
    the wire format cannot distinguish the two and no account quotes money in
    whole units.

    Args:
        money_digits: The exponent reported alongside the amount, or 0 if the
            server omitted it.

    Returns:
        The divisor to apply to the scaled integer.
    """
    return 10 ** (money_digits or DEFAULT_MONEY_DIGITS)


def timestamp_to_datetime(timestamp_ms: int) -> datetime:
    """Convert a millisecond UTC timestamp to an aware datetime.

    Args:
        timestamp_ms: Milliseconds since the Unix epoch, as sent by the server.

    Returns:
        The equivalent timezone-aware datetime in UTC.
    """
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
