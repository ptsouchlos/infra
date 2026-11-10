#!/usr/bin/env bash
# Build an .msi with WiX from a caller-supplied .wxs and a directory of prebuilt binaries.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   BIN_DIR WXS NAME VERSION ARCH OUT_DIR EXTRA_DEFINES
# The .wxs receives these preprocessor variables, so it can stay free of paths and versions:
#   $(BinDir) the directory holding the binaries, $(Version) the MSI version (1.2.3, with any
#   prerelease or build suffix dropped, since Windows Installer wants up to four numeric fields).
# EXTRA_DEFINES is optional extra `-d` definitions, one NAME=value per line.
# ARCH is x64 or arm64 (default x64) and goes to `wix build -arch`.
# SIGNING GOES HERE LATER: sign the binaries before `wix build` and the .msi after it, for
# example with `signtool sign` or Azure Trusted Signing. Nothing is signed today.
# Writes asset= and checksum= to $GITHUB_OUTPUT.
set -euo pipefail

: "${BIN_DIR:?BIN_DIR is required}"
: "${WXS:?WXS is required}"
: "${NAME:?NAME is required}"
: "${VERSION:?VERSION is required}"
: "${ARCH:=x64}"
: "${OUT_DIR:=dist}"
: "${EXTRA_DEFINES:=}"
: "${GITHUB_OUTPUT:=/dev/null}"

if [ ! -d "$BIN_DIR" ]; then
    echo "::error::bin-dir '$BIN_DIR' does not exist"
    exit 1
fi
if [ ! -f "$WXS" ]; then
    echo "::error::wxs '$WXS' does not exist"
    exit 1
fi
case "$ARCH" in
    x64 | arm64) ;;
    *)
        echo "::error::arch must be x64 or arm64 (got '$ARCH')"
        exit 1
        ;;
esac

# 1.2.3-rc.1+build -> 1.2.3
msi_version="${VERSION%%[-+]*}"
if ! printf '%s' "$msi_version" | grep -Eq '^[0-9]+(\.[0-9]+){0,3}$'; then
    echo "::error::version '$VERSION' does not start with up to four dotted numbers"
    exit 1
fi

mkdir -p "$OUT_DIR"
out="$(cd "$OUT_DIR" && pwd)"
asset="$out/$NAME.msi"
rm -f "$asset"

# wix is a native Windows program: hand it Windows paths when running under Git Bash.
winpath() {
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -w "$1"
    else
        printf '%s\n' "$1"
    fi
}
bin_abs="$(cd "$BIN_DIR" && pwd)"

args=(build -arch "$ARCH" -d "BinDir=$(winpath "$bin_abs")" -d "Version=$msi_version")
while IFS= read -r line; do
    if [ -n "$line" ]; then
        args+=(-d "$line")
    fi
done <<EOF
$EXTRA_DEFINES
EOF
args+=(-o "$(winpath "$asset")" "$(winpath "$WXS")")

echo "::group::wix build"
wix "${args[@]}"
echo "::endgroup::"
if [ ! -f "$asset" ]; then
    echo "::error::wix did not write '$asset'"
    exit 1
fi

base="$(basename "$asset")"
if command -v sha256sum >/dev/null 2>&1; then
    (cd "$out" && sha256sum "$base" >"$base.sha256")
else
    (cd "$out" && shasum -a 256 "$base" >"$base.sha256")
fi

{
    echo "asset=$asset"
    echo "checksum=$asset.sha256"
} >>"$GITHUB_OUTPUT"
