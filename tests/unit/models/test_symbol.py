"""Tests for symbol models."""

from __future__ import annotations

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

    def test_volume_to_lots_uses_lot_size(self) -> None:
        """Test volume_to_lots uses symbol's lot_size."""
        symbol = Symbol(
            symbol_id=1,
            digits=5,
            pip_position=4,
            lot_size=100000,  # Standard forex lot
            min_volume=1000,
            max_volume=10000000,
            step_volume=1000,
            trading_mode=TradingMode.ENABLED,
            swap_long=0.0,
            swap_short=0.0,
        )

        # 100000 cents / 100000 lot_size = 1 lot
        assert symbol.volume_to_lots(100000) == 1.0
        # 10000 cents / 100000 lot_size = 0.1 lots
        assert symbol.volume_to_lots(10000) == 0.1
        # 1000 cents / 100000 lot_size = 0.01 lots
        assert symbol.volume_to_lots(1000) == 0.01

    def test_lots_to_volume_uses_lot_size(self) -> None:
        """Test lots_to_volume uses symbol's lot_size."""
        symbol = Symbol(
            symbol_id=1,
            digits=5,
            pip_position=4,
            lot_size=100000,  # Standard forex lot
            min_volume=1000,
            max_volume=10000000,
            step_volume=1000,
            trading_mode=TradingMode.ENABLED,
            swap_long=0.0,
            swap_short=0.0,
        )

        # 1 lot * 100000 lot_size = 100000 cents
        assert symbol.lots_to_volume(1.0) == 100000
        # 0.1 lots * 100000 lot_size = 10000 cents
        assert symbol.lots_to_volume(0.1) == 10000
        # 0.01 lots * 100000 lot_size = 1000 cents
        assert symbol.lots_to_volume(0.01) == 1000

    def test_volume_to_lots_different_lot_sizes(self) -> None:
        """Test volume_to_lots with different lot sizes."""
        # CFD with smaller lot size
        cfd_symbol = Symbol(
            symbol_id=2,
            digits=2,
            pip_position=0,
            lot_size=100,  # Smaller lot size
            min_volume=1,
            max_volume=10000,
            step_volume=1,
            trading_mode=TradingMode.ENABLED,
            swap_long=0.0,
            swap_short=0.0,
        )

        # 100 cents / 100 lot_size = 1 lot
        assert cfd_symbol.volume_to_lots(100) == 1.0
        # 50 cents / 100 lot_size = 0.5 lots
        assert cfd_symbol.volume_to_lots(50) == 0.5

    def test_volume_roundtrip(self) -> None:
        """Test that volume conversion is reversible."""
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

        original_lots = 0.5
        volume = symbol.lots_to_volume(original_lots)
        result = symbol.volume_to_lots(volume)
        assert result == original_lots
