"""Tests for symbol models."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from ctrader_api_client.enums import TradingMode
from ctrader_api_client.models import Symbol, SymbolInfo


class TestSymbolInfo:
    """Tests for SymbolInfo model."""

    def test_from_proto_maps_all_fields(self) -> None:
        """Test that from_proto correctly maps all proto fields."""
        proto = MagicMock()
        proto.symbol_id = 1
        proto.symbol_name = "EURUSD"
        proto.enabled = True
        proto.base_asset_id = 10
        proto.quote_asset_id = 20
        proto.symbol_category_id = 5
        proto.description = "Euro vs US Dollar"

        info = SymbolInfo.from_proto(proto)

        assert info.symbol_id == 1
        assert info.name == "EURUSD"
        assert info.enabled is True
        assert info.base_asset_id == 10
        assert info.quote_asset_id == 20
        assert info.category_id == 5
        assert info.description == "Euro vs US Dollar"

    def test_from_proto_handles_missing_category(self) -> None:
        """Test that from_proto handles missing category ID."""
        proto = MagicMock()
        proto.symbol_id = 1
        proto.symbol_name = "EURUSD"
        proto.enabled = True
        proto.base_asset_id = 10
        proto.quote_asset_id = 20
        proto.symbol_category_id = 0
        proto.description = None

        info = SymbolInfo.from_proto(proto)

        assert info.category_id is None
        assert info.description == ""


class TestSymbol:
    """Tests for Symbol model."""

    def test_from_proto_maps_all_fields(self) -> None:
        """Test that from_proto correctly maps all proto fields."""
        proto = MagicMock()
        proto.symbol_id = 1
        proto.digits = 5
        proto.pip_position = 4
        proto.lot_size = 100000
        proto.min_volume = 1000
        proto.max_volume = 10000000
        proto.step_volume = 1000
        proto.trading_mode = 0  # ENABLED
        proto.swap_long = -1.5
        proto.swap_short = 0.5
        proto.commission = 50
        proto.max_exposure = 1000000
        proto.leverage_id = 10
        proto.enable_short_selling = True
        proto.guaranteed_stop_loss = False
        proto.sl_distance = 10
        proto.tp_distance = 10
        proto.schedule_time_zone = "UTC"
        proto.measurement_units = ""

        symbol = Symbol.from_proto(proto)

        assert symbol.symbol_id == 1
        assert symbol.digits == 5
        assert symbol.pip_position == 4
        assert symbol.lot_size == 100000
        assert symbol.min_volume == 1000
        assert symbol.max_volume == 10000000
        assert symbol.step_volume == 1000
        assert symbol.trading_mode == TradingMode.ENABLED
        assert symbol.swap_long == -1.5
        assert symbol.swap_short == 0.5
        assert symbol.commission == 50
        assert symbol.max_exposure == 1000000
        assert symbol.leverage_id == 10
        assert symbol.enable_short_selling is True
        assert symbol.guaranteed_stop_loss is False
        assert symbol.sl_distance == 10
        assert symbol.tp_distance == 10
        assert symbol.schedule_timezone == "UTC"

    def test_from_proto_maps_trading_modes(self) -> None:
        """Test that all trading modes are correctly mapped."""
        base_proto = MagicMock()
        base_proto.symbol_id = 1
        base_proto.digits = 5
        base_proto.pip_position = 4
        base_proto.lot_size = 100000
        base_proto.min_volume = 1000
        base_proto.max_volume = 10000000
        base_proto.step_volume = 1000
        base_proto.swap_long = 0.0
        base_proto.swap_short = 0.0
        base_proto.commission = 0
        base_proto.max_exposure = 0
        base_proto.leverage_id = 0
        base_proto.enable_short_selling = True
        base_proto.guaranteed_stop_loss = False
        base_proto.sl_distance = 0
        base_proto.tp_distance = 0
        base_proto.schedule_time_zone = ""
        base_proto.measurement_units = ""

        test_cases = [
            (0, TradingMode.ENABLED),
            (1, TradingMode.DISABLED_WITHOUT_PENDINGS_EXECUTION),
            (2, TradingMode.DISABLED_WITH_PENDINGS_EXECUTION),
            (3, TradingMode.CLOSE_ONLY),
        ]

        for proto_value, expected_mode in test_cases:
            base_proto.trading_mode = proto_value
            symbol = Symbol.from_proto(base_proto)
            assert symbol.trading_mode == expected_mode

    def test_price_to_decimal_5_digits(self) -> None:
        """Test price_to_decimal with 5 decimal places."""
        symbol = Symbol(
            symbol_id=1,
            digits=5,
            pip_position=4,
            lot_size=100000,
            min_volume=1000,
            max_volume=10000000,
            step_volume=1000,
            trading_mode=TradingMode.ENABLED,
            swap_long=0.0,
            swap_short=0.0,
        )

        # 1.12345 represented as 112345
        result = symbol.price_to_decimal(112345)
        assert result == Decimal("1.12345")

    def test_price_to_decimal_3_digits(self) -> None:
        """Test price_to_decimal with 3 decimal places (JPY pairs)."""
        symbol = Symbol(
            symbol_id=1,
            digits=3,
            pip_position=2,
            lot_size=100000,
            min_volume=1000,
            max_volume=10000000,
            step_volume=1000,
            trading_mode=TradingMode.ENABLED,
            swap_long=0.0,
            swap_short=0.0,
        )

        # 150.123 represented as 150123
        result = symbol.price_to_decimal(150123)
        assert result == Decimal("150.123")

    def test_decimal_to_price_5_digits(self) -> None:
        """Test decimal_to_price with 5 decimal places."""
        symbol = Symbol(
            symbol_id=1,
            digits=5,
            pip_position=4,
            lot_size=100000,
            min_volume=1000,
            max_volume=10000000,
            step_volume=1000,
            trading_mode=TradingMode.ENABLED,
            swap_long=0.0,
            swap_short=0.0,
        )

        result = symbol.decimal_to_price(Decimal("1.12345"))
        assert result == 112345

    def test_decimal_to_price_3_digits(self) -> None:
        """Test decimal_to_price with 3 decimal places."""
        symbol = Symbol(
            symbol_id=1,
            digits=3,
            pip_position=2,
            lot_size=100000,
            min_volume=1000,
            max_volume=10000000,
            step_volume=1000,
            trading_mode=TradingMode.ENABLED,
            swap_long=0.0,
            swap_short=0.0,
        )

        result = symbol.decimal_to_price(Decimal("150.123"))
        assert result == 150123

    def test_volume_to_lots_full_lot(self) -> None:
        """Test volume_to_lots for 1 full lot (100 cents)."""
        result = Symbol.volume_to_lots(100)
        assert result == Decimal("1")

    def test_volume_to_lots_mini_lot(self) -> None:
        """Test volume_to_lots for 0.1 lots (10 cents)."""
        result = Symbol.volume_to_lots(10)
        assert result == Decimal("0.1")

    def test_volume_to_lots_micro_lot(self) -> None:
        """Test volume_to_lots for 0.01 lots (1 cent)."""
        result = Symbol.volume_to_lots(1)
        assert result == Decimal("0.01")

    def test_lots_to_volume_full_lot(self) -> None:
        """Test lots_to_volume for 1 full lot."""
        result = Symbol.lots_to_volume(Decimal("1"))
        assert result == 100

    def test_lots_to_volume_mini_lot(self) -> None:
        """Test lots_to_volume for 0.1 lots."""
        result = Symbol.lots_to_volume(Decimal("0.1"))
        assert result == 10

    def test_lots_to_volume_micro_lot(self) -> None:
        """Test lots_to_volume for 0.01 lots."""
        result = Symbol.lots_to_volume(Decimal("0.01"))
        assert result == 1

    def test_price_roundtrip(self) -> None:
        """Test that price conversion is reversible."""
        symbol = Symbol(
            symbol_id=1,
            digits=5,
            pip_position=4,
            lot_size=100000,
            min_volume=1000,
            max_volume=10000000,
            step_volume=1000,
            trading_mode=TradingMode.ENABLED,
            swap_long=0.0,
            swap_short=0.0,
        )

        original_price = Decimal("1.23456")
        raw = symbol.decimal_to_price(original_price)
        result = symbol.price_to_decimal(raw)
        assert result == original_price

    def test_volume_roundtrip(self) -> None:
        """Test that volume conversion is reversible."""
        original_lots = Decimal("0.5")
        volume = Symbol.lots_to_volume(original_lots)
        result = Symbol.volume_to_lots(volume)
        assert result == original_lots
