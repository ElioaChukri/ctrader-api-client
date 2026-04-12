from __future__ import annotations

from enum import Enum, StrEnum


class Environment(StrEnum):
    """Trading environment."""

    DEMO = "DEMO"
    LIVE = "LIVE"


class ExecutionType(Enum):
    """Type of execution event."""

    ORDER_ACCEPTED = "ORDER_ACCEPTED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_REPLACED = "ORDER_REPLACED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_EXPIRED = "ORDER_EXPIRED"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_CANCEL_REJECTED = "ORDER_CANCEL_REJECTED"
    ORDER_PARTIAL_FILL = "ORDER_PARTIAL_FILL"
    SWAP = "SWAP"
    DEPOSIT_WITHDRAW = "DEPOSIT_WITHDRAW"
    BONUS_DEPOSIT_WITHDRAW = "BONUS_DEPOSIT_WITHDRAW"


class OrderSide(Enum):
    """Order side (direction)."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Order type."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    MARKET_RANGE = "MARKET_RANGE"
    STOP_LOSS_TAKE_PROFIT = "STOP_LOSS_TAKE_PROFIT"


class OrderStatus(Enum):
    """Order status."""

    ACCEPTED = "ACCEPTED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class PositionStatus(Enum):
    """Position status."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CREATED = "CREATED"
    ERROR = "ERROR"


class TimeInForce(Enum):
    """Order time in force."""

    GOOD_TILL_CANCEL = "GTC"
    GOOD_TILL_DATE = "GTD"
    IMMEDIATE_OR_CANCEL = "IOC"
    FILL_OR_KILL = "FOK"
    MARKET_ON_OPEN = "MOO"


class DealStatus(Enum):
    """Deal execution status."""

    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    INTERNALLY_REJECTED = "INTERNALLY_REJECTED"
    ERROR = "ERROR"
    MISSED = "MISSED"


class AccessRights(Enum):
    """Account access rights."""

    FULL_ACCESS = "FULL_ACCESS"
    CLOSE_ONLY = "CLOSE_ONLY"
    NO_TRADING = "NO_TRADING"
    NO_LOGIN = "NO_LOGIN"


class AccountType(Enum):
    """Account type."""

    HEDGED = "HEDGED"
    NETTED = "NETTED"
    SPREAD_BETTING = "SPREAD_BETTING"


class TradingMode(Enum):
    """Symbol trading mode."""

    ENABLED = "ENABLED"
    DISABLED_WITHOUT_PENDINGS_EXECUTION = "DISABLED_WITHOUT_PENDINGS"
    DISABLED_WITH_PENDINGS_EXECUTION = "DISABLED_WITH_PENDINGS"
    CLOSE_ONLY = "CLOSE_ONLY"


class TrendbarPeriod(Enum):
    """Trendbar/candle period."""

    M1 = "M1"
    M2 = "M2"
    M3 = "M3"
    M4 = "M4"
    M5 = "M5"
    M10 = "M10"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    H12 = "H12"
    D1 = "D1"
    W1 = "W1"
    MN1 = "MN1"


class StopTriggerMethod(Enum):
    """Method for triggering stop orders."""

    TRADE = "TRADE"
    OPPOSITE = "OPPOSITE"
    DOUBLE_TRADE = "DOUBLE_TRADE"
    DOUBLE_OPPOSITE = "DOUBLE_OPPOSITE"
