import re
from pathlib import Path


PROTO_DIR = Path(__file__).parent.parent / "src/ctrader_api_client/_internal/proto"

# Import statements to add to each file
IMPORTS_FOR_MESSAGES = """\
from .OpenApiModelMessages import (
    ProtoOAPayloadType,
    ProtoOAOrderType,
    ProtoOATradeSide,
    ProtoOATimeInForce,
    ProtoOAExecutionType,
    ProtoOAOrderTriggerMethod,
    ProtoOATrendbarPeriod,
    ProtoOAQuoteType,
    ProtoOAClientPermissionScope,
    ProtoOAPosition,
    ProtoOAOrder,
    ProtoOADeal,
    ProtoOATrader,
    ProtoOAAsset,
    ProtoOALightSymbol,
    ProtoOAArchivedSymbol,
    ProtoOASymbol,
    ProtoOAAssetClass,
    ProtoOASymbolCategory,
    ProtoOATrendbar,
    ProtoOATickData,
    ProtoOADepthQuote,
    ProtoOACtidTraderAccount,
    ProtoOACtidProfile,
    ProtoOAExpectedMargin,
    ProtoOADepositWithdraw,
    ProtoOABonusDepositWithdraw,
    ProtoOAMarginCall,
    ProtoOADynamicLeverage,
    ProtoOADealOffset,
    ProtoOAPositionUnrealizedPnL,
)
"""

IMPORTS_FOR_COMMON_MESSAGES = """\
from .OpenApiCommonModelMessages import ProtoPayloadType
"""


def fix_file(filepath: Path, imports: str) -> None:
    """Add imports to a generated file."""
    content = filepath.read_text()

    # Check if already fixed
    if "from .OpenApi" in content:
        print(f"  {filepath.name}: already fixed")
        return

    # Insert imports after "import betterproto"
    marker = "import betterproto\n"
    if marker in content:
        content = content.replace(marker, marker + imports)
        filepath.write_text(content)
        print(f"  {filepath.name}: fixed")
    else:
        print(f"  {filepath.name}: marker not found, skipping")


def extract_exports(filepath: Path) -> list[str]:
    """Extract class and enum names from a generated file."""

    content = filepath.read_text()
    # Match class definitions (both regular and dataclass)
    pattern = r"^class\s+(\w+)\s*[\(:]"
    matches = re.findall(pattern, content, re.MULTILINE)
    return matches


def create_init(proto_dir: Path) -> None:
    """Create __init__.py that re-exports everything with explicit __all__."""
    # Files to export from (in dependency order)
    modules = [
        "OpenApiCommonModelMessages",
        "OpenApiCommonMessages",
        "OpenApiModelMessages",
        "OpenApiMessages",
    ]

    all_exports: dict[str, list[str]] = {}

    for module in modules:
        filepath = proto_dir / f"{module}.py"
        if filepath.exists():
            exports = extract_exports(filepath)
            all_exports[module] = exports
            print(f"  {module}: found {len(exports)} exports")

    # Build __init__.py content
    lines = [
        '"""Generated protobuf messages for cTrader Open API."""',
        "",
    ]

    # Add imports
    for module, exports in all_exports.items():
        if exports:
            lines.append(f"from .{module} import (")
            for name in sorted(exports):
                lines.append(f"    {name},")
            lines.append(")")
            lines.append("")

    # Add __all__
    all_names = []
    for exports in all_exports.values():
        all_names.extend(exports)

    lines.append("__all__ = [")
    for name in sorted(all_names):
        lines.append(f'    "{name}",')
    lines.append("]")

    init_path = proto_dir / "__init__.py"
    init_path.write_text("\n".join(lines) + "\n")
    print(f"  __init__.py: created with {len(all_names)} exports")


def main() -> None:
    print(f"Fixing proto imports in {PROTO_DIR}")

    # Fix OpenApiMessages.py (uses types from OpenApiModelMessages)
    messages_file = PROTO_DIR / "OpenApiMessages.py"
    if messages_file.exists():
        fix_file(messages_file, IMPORTS_FOR_MESSAGES)

    # Fix OpenApiCommonMessages.py (uses types from OpenApiCommonModelMessages)
    common_messages_file = PROTO_DIR / "OpenApiCommonMessages.py"
    if common_messages_file.exists():
        fix_file(common_messages_file, IMPORTS_FOR_COMMON_MESSAGES)

    # Create __init__.py
    create_init(PROTO_DIR)

    print("Done")


if __name__ == "__main__":
    main()
