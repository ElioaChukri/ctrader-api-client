#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cat "$SCRIPT_DIR/SOURCE")"
VERSION="${1:-main}"
VENDOR_DIR="$SCRIPT_DIR/vendor"
TEMP_DIR=$(mktemp -d)

trap 'rm -rf "$TEMP_DIR"' EXIT

echo "Fetching $REPO @ $VERSION..."
git -c advice.detachedHead=false clone --depth 1 --branch "$VERSION" "$REPO" "$TEMP_DIR"

rm -rf "$VENDOR_DIR"
mkdir -p "$VENDOR_DIR"

# Copy the proto files from TEMP_DIR to VENDOR_DIR
find "$TEMP_DIR" -name "*.proto" -exec cp {} "$VENDOR_DIR/" \;

proto_count=$(find "$VENDOR_DIR" -maxdepth 1 -name "*.proto" | wc -l)
if [ "$proto_count" -eq 0 ]; then
    echo "Error: No .proto files found"
    exit 1
fi

echo "$VERSION" > "$SCRIPT_DIR/VERSION"

echo "Updated to $VERSION"
echo "Files:"
ls -1 "$VENDOR_DIR"
