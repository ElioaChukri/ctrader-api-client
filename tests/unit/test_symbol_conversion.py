"""Symbol trading arithmetic and the translation of symbol definitions."""

from __future__ import annotations

from decimal import Decimal

import pytest

from ctrader_api_client._internal.proto import ProtoOALightSymbol, ProtoOASymbol, ProtoOATradingMode
from ctrader_api_client.enums import TradingMode
from ctrader_api_client.models import Symbol, SymbolInfo


def forex_symbol(**overrides: object) -> Symbol:
    settings: dict[str, object] = {
        "symbol_id": 270,
        "digits": 5,
        "pip_position": 4,
        "lot_size": 10_000_000,
        "min_volume": 100_000,
        "max_volume": 1_000_000_000,
        "step_volume": 100_000,
        "trading_mode": TradingMode.ENABLED,
        "swap_long": Decimal("-1.5"),
        "swap_short": Decimal("0.5"),
    }
    settings.update(overrides)
    return Symbol(**settings)  # type: ignore[arg-type]


def test_volume_is_reported_in_lots() -> None:
    symbol = forex_symbol(lot_size=10_000_000)

    assert symbol.volume_to_lots(5_000_000) == Decimal("0.5")


def test_lots_are_converted_to_the_volume_the_api_expects() -> None:
    symbol = forex_symbol(lot_size=10_000_000)

    assert symbol.lots_to_volume(Decimal("2.5")) == 25_000_000


def test_a_lot_size_that_does_not_divide_evenly_is_truncated() -> None:
    """Volume must be a whole number of cents; fractions cannot be sent."""
    symbol = forex_symbol(lot_size=10_000_000)

    assert symbol.lots_to_volume(Decimal("0.00000015")) == 1


def test_converting_lots_and_back_returns_the_original_volume() -> None:
    symbol = forex_symbol(lot_size=10_000_000)

    assert symbol.lots_to_volume(symbol.volume_to_lots(1_234_500)) == 1_234_500


@pytest.mark.parametrize(
    ("digits", "price", "expected"),
    [
        (5, Decimal("1.234567"), Decimal("1.23457")),
        (3, Decimal("1.234567"), Decimal("1.235")),
        (2, Decimal("1.005"), Decimal("1.00")),
        (5, Decimal("1.2"), Decimal("1.20000")),
    ],
)
def test_prices_are_quantized_to_the_symbol_precision(digits: int, price: Decimal, expected: Decimal) -> None:
    symbol = forex_symbol(digits=digits)

    assert symbol.quantize_price(price) == expected
    assert str(symbol.quantize_price(price)) == str(expected)


def test_a_symbol_definition_keeps_its_trading_limits() -> None:
    symbol = Symbol.from_proto(
        ProtoOASymbol(
            symbol_id=270,
            digits=5,
            pip_position=4,
            lot_size=10_000_000,
            min_volume=100_000,
            max_volume=1_000_000_000,
            step_volume=100_000,
            trading_mode=ProtoOATradingMode.ENABLED,
            swap_long=-1.5,
            swap_short=0.5,
        )
    )

    assert (symbol.min_volume, symbol.max_volume, symbol.step_volume) == (100_000, 1_000_000_000, 100_000)
    assert symbol.swap_long == Decimal("-1.5")
    assert symbol.swap_short == Decimal("0.5")


@pytest.mark.parametrize(
    ("proto_mode", "expected"),
    [
        (ProtoOATradingMode.ENABLED, TradingMode.ENABLED),
        (ProtoOATradingMode.CLOSE_ONLY_MODE, TradingMode.CLOSE_ONLY),
        (
            ProtoOATradingMode.DISABLED_WITH_PENDINGS_EXECUTION,
            TradingMode.DISABLED_WITH_PENDINGS_EXECUTION,
        ),
        (
            ProtoOATradingMode.DISABLED_WITHOUT_PENDINGS_EXECUTION,
            TradingMode.DISABLED_WITHOUT_PENDINGS_EXECUTION,
        ),
    ],
)
def test_the_trading_mode_is_translated(proto_mode: ProtoOATradingMode, expected: TradingMode) -> None:
    symbol = Symbol.from_proto(ProtoOASymbol(symbol_id=1, trading_mode=proto_mode))

    assert symbol.trading_mode == expected


def test_optional_symbol_fields_left_at_zero_are_reported_as_absent() -> None:
    symbol = Symbol.from_proto(ProtoOASymbol(symbol_id=1))

    assert symbol.max_exposure is None
    assert symbol.leverage_id is None


def test_a_symbol_listing_entry_keeps_its_identity() -> None:
    info = SymbolInfo.from_proto(
        ProtoOALightSymbol(
            symbol_id=270,
            symbol_name="EURUSD",
            enabled=True,
            base_asset_id=1,
            quote_asset_id=2,
            symbol_category_id=5,
            description="Euro vs US Dollar",
        )
    )

    assert (info.symbol_id, info.name, info.enabled) == (270, "EURUSD", True)
    assert (info.base_asset_id, info.quote_asset_id) == (1, 2)
    assert info.category_id == 5
    assert info.description == "Euro vs US Dollar"


def test_a_listing_entry_without_a_category_reports_none() -> None:
    info = SymbolInfo.from_proto(ProtoOALightSymbol(symbol_id=1, symbol_name="X"))

    assert info.category_id is None
    assert info.description == ""
