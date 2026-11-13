#!/usr/bin/env bash
# Build an .msi with WiX from a caller-supplied .wxs and a directory of prebuilt binaries.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   BIN_DIR WXS NAME VERSION ARCH OUT_DIR EXTRA_DEFINES WIX_ACCEPT_EULA
# WIX_ACCEPT_EULA is the WiX Open Source Maintenance Fee EULA id (wix7 for WiX 7), passed as
# `wix build -acceptEula <id>`. WiX 7 refuses to build without it; empty omits the switch.
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
: "${WIX_ACCEPT_EULA:=}"
: "${SIGN_CERT:=}"
: "${SIGN_PASSWORD:=}"
: "${SIGN_TIMESTAMP_URL:=http://timestamp.digicert.com}"
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

work=""
trap '[ -n "$work" ] && rm -rf "$work"' EXIT

find_signtool() {
    if command -v signtool >/dev/null 2>&1; then
        command -v signtool
        return
    fi
    if command -v signtool.exe >/dev/null 2>&1; then
        command -v signtool.exe
        return
    fi
    local sdk_arch="$ARCH"
    local found=""
    found="$(find "/c/Program Files (x86)/Windows Kits/10/bin" -path "*/$sdk_arch/signtool.exe" 2>/dev/null | sort -V | tail -n1 || true)"
    printf '%s\n' "$found"
}

sign_file() {
    local signtool="$1" pfx="$2" target="$3"
    local sargs=(sign /fd SHA256 /tr "$SIGN_TIMESTAMP_URL" /td SHA256 /f "$(winpath "$pfx")")
    if [ -n "$SIGN_PASSWORD" ]; then
        sargs+=(/p "$SIGN_PASSWORD")
    fi
    sargs+=("$(winpath "$target")")
    "$signtool" "${sargs[@]}"
}

signtool_bin=""
pfx_file=""
if [ -n "$SIGN_CERT" ]; then
    signtool_bin="$(find_signtool)"
    if [ -z "$signtool_bin" ]; then
        echo "::error::signtool not found on PATH or in Windows Kits 10"
        exit 1
    fi
    work="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/win-sign.XXXXXX")"
    if [ -f "$SIGN_CERT" ]; then
        pfx_file="$SIGN_CERT"
    else
        pfx_file="$work/cert.pfx"
        if ! printf '%s' "$SIGN_CERT" | tr -d '[:space:]' | base64 -d >"$pfx_file" 2>/dev/null; then
            printf '%s' "$SIGN_CERT" | tr -d '[:space:]' | base64 --decode >"$pfx_file"
        fi
    fi
    mkdir -p "$work/bin"
    cp "$bin_abs"/* "$work/bin/"
    bin_abs="$work/bin"
    echo "::group::signtool binaries"
    for f in "$bin_abs"/*; do
        case "$f" in
            *.exe | *.dll) sign_file "$signtool_bin" "$pfx_file" "$f" ;;
        esac
    done
    echo "::endgroup::"
fi

args=(build)
if [ -n "$WIX_ACCEPT_EULA" ]; then
    args+=(-acceptEula "$WIX_ACCEPT_EULA")
fi
args+=(-arch "$ARCH" -d "BinDir=$(winpath "$bin_abs")" -d "Version=$msi_version")
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

if [ -n "$signtool_bin" ]; then
    echo "::group::signtool msi"
    sign_file "$signtool_bin" "$pfx_file" "$asset"
    echo "::endgroup::"
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
