#!/usr/bin/env bash
# Build one Rust target in release mode, package its binaries and write the checksum.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   TARGET BIN BINS NAME ARCHIVE WORKING_DIRECTORY CARGO_ARGS OUT_DIR (and the caller's CARGO_TARGET_DIR)
# BINS is a whitespace-separated list and wins over BIN; the default NAME uses the first binary.
# Writes asset=, checksum= and bin-dir= (the staged binaries) to $GITHUB_OUTPUT.
set -euo pipefail

: "${TARGET:?TARGET is required}"
: "${BIN:=}"
: "${BINS:=}"
: "${NAME:=}"
: "${ARCHIVE:=auto}"
: "${WORKING_DIRECTORY:=.}"
: "${CARGO_ARGS:=}"
: "${OUT_DIR:=dist}"
: "${GITHUB_OUTPUT:=/dev/null}"

if [ -z "$BINS" ]; then
    BINS="$BIN"
fi
read -r -a bins <<<"$BINS"
if [ "${#bins[@]}" -eq 0 ]; then
    echo "::error::set bin or bins to the binaries to package"
    exit 1
fi

if [ -z "$NAME" ]; then
    NAME="${bins[0]}-$TARGET"
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
if [ "$ARCHIVE" = none ] && [ "${#bins[@]}" -gt 1 ]; then
    echo "::error::archive 'none' can only hold one binary; use tar.gz, zip or auto for several"
    exit 1
fi

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
# Stage outside OUT_DIR so globbing the assets there never picks up the bare binaries.
stage="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/cargo-release.XXXXXX")"
if command -v cygpath >/dev/null 2>&1; then
    stage="$(cygpath -m "$stage")"
fi
files=()
for b in "${bins[@]}"; do
    binary="$release_dir/$b$exe"
    if [ ! -f "$binary" ]; then
        echo "::error::expected binary '$binary' was not built; check that bin matches the crate's binary name"
        exit 1
    fi
    cp "$binary" "$stage/$b$exe"
    files+=("$b$exe")
done

echo "::group::package"
case "$ARCHIVE" in
    tar.gz)
        asset="$out/$NAME.tar.gz"
        tar -C "$stage" -czf "$asset" "${files[@]}"
        ;;
    zip)
        asset="$out/$NAME.zip"
        rm -f "$asset"
        (cd "$stage" && 7z a -tzip "$asset" "${files[@]}" >/dev/null)
        ;;
    none)
        asset="$out/$NAME$exe"
        cp "$stage/${files[0]}" "$asset"
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
    echo "bin-dir=$stage"
} >>"$GITHUB_OUTPUT"
