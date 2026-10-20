#!/usr/bin/env bash
# Build one Rust target in release mode, package the binary and write its checksum.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   TARGET BIN NAME ARCHIVE WORKING_DIRECTORY CARGO_ARGS OUT_DIR (and the caller's CARGO_TARGET_DIR)
# Writes asset= and checksum= to $GITHUB_OUTPUT.
set -euo pipefail

: "${TARGET:?TARGET is required}"
: "${BIN:?BIN is required}"
: "${NAME:=}"
: "${ARCHIVE:=auto}"
: "${WORKING_DIRECTORY:=.}"
: "${CARGO_ARGS:=}"
: "${OUT_DIR:=dist}"
: "${GITHUB_OUTPUT:=/dev/null}"

if [ -z "$NAME" ]; then
    NAME="$BIN-$TARGET"
fi

exe=""
case "$TARGET" in
    *windows*) exe=".exe" ;;
esac

if [ "$ARCHIVE" = auto ]; then
    if [ -n "$exe" ]; then
        ARCHIVE=zip
    else
        ARCHIVE=tar.gz
    fi
fi
case "$ARCHIVE" in
    tar.gz | zip | none) ;;
    *)
        echo "::error::archive '$ARCHIVE' is not supported (auto|tar.gz|zip|none)"
        exit 1
        ;;
esac

# OUT_DIR is relative to the caller's directory, not the crate's.
mkdir -p "$OUT_DIR"
out="$(cd "$OUT_DIR" && pwd)"

cd "$WORKING_DIRECTORY"

build=(cargo build --release --target "$TARGET")
if [ -n "$CARGO_ARGS" ]; then
    read -r -a extra <<<"$CARGO_ARGS"
    build+=("${extra[@]}")
fi

echo "::group::build"
"${build[@]}"
echo "::endgroup::"

release_dir="${CARGO_TARGET_DIR:-target}/$TARGET/release"
binary="$release_dir/$BIN$exe"
if [ ! -f "$binary" ]; then
    echo "::error::expected binary '$binary' was not built; check that bin matches the crate's binary name"
    exit 1
fi

echo "::group::package"
case "$ARCHIVE" in
    tar.gz)
        asset="$out/$NAME.tar.gz"
        tar -C "$release_dir" -czf "$asset" "$BIN"
        ;;
    zip)
        asset="$out/$NAME.zip"
        rm -f "$asset"
        (cd "$release_dir" && 7z a -tzip "$asset" "$BIN$exe" >/dev/null)
        ;;
    none)
        asset="$out/$NAME$exe"
        cp "$binary" "$asset"
        ;;
esac

checksum="$asset.sha256"
base="$(basename "$asset")"
if command -v sha256sum >/dev/null 2>&1; then
    (cd "$out" && sha256sum "$base" >"$base.sha256")
else
    (cd "$out" && shasum -a 256 "$base" >"$base.sha256")
fi
echo "::endgroup::"

{
    echo "asset=$asset"
    echo "checksum=$checksum"
} >>"$GITHUB_OUTPUT"
