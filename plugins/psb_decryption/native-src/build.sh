#!/usr/bin/env bash
set -euo pipefail
RUST_ROOT="$(cd "$(dirname "$0")" && pwd)"
PACKAGE_DIR="$(dirname "$RUST_ROOT")"
PROJECT_ROOT="$(cd "$PACKAGE_DIR/../.." && pwd)"
export CARGO_TARGET_DIR="$RUST_ROOT/target"
cargo build --manifest-path "$RUST_ROOT/Cargo.toml" --workspace --release --locked
case "$(uname -s)" in
  Linux*) source="$CARGO_TARGET_DIR/release/lib_freemote_native.so" ;;
  Darwin*) source="$CARGO_TARGET_DIR/release/lib_freemote_native.dylib" ;;
  *) echo "Unsupported platform" >&2; exit 1 ;;
esac
target="$PACKAGE_DIR/_freemote_native.so"
cp "$source" "$target"
(cd "$PROJECT_ROOT" && python -c "from plugins.psb_decryption import _native; assert _native.available('psp_lzss_unpack'), _native.load_error()")
echo "Built $target"