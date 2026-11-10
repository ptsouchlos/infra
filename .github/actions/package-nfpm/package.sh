#!/usr/bin/env bash
# Build .deb and/or .rpm packages from prebuilt files with nFPM and write their checksums.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   CONFIG BIN_DIR VERSION ARCH NAME FORMATS OUT_DIR
# nfpm must already be on PATH (see install.sh). The config is the caller's own nFPM YAML and
# may use ${PKG_BIN_DIR}, ${PKG_VERSION} and ${PKG_ARCH}; nFPM maps PKG_ARCH (amd64|arm64) to
# each format's own arch name (x86_64|aarch64 for rpm).
# Writes assets= (newline-separated paths) and checksums= to $GITHUB_OUTPUT.
set -euo pipefail

: "${CONFIG:?CONFIG is required}"
: "${BIN_DIR:?BIN_DIR is required}"
: "${VERSION:?VERSION is required}"
: "${ARCH:?ARCH is required}"
: "${NAME:?NAME is required}"
: "${FORMATS:=deb rpm}"
: "${OUT_DIR:=dist}"
: "${GITHUB_OUTPUT:=/dev/null}"

case "$ARCH" in
    x86_64 | amd64) pkg_arch=amd64 ;;
    aarch64 | arm64) pkg_arch=arm64 ;;
    *)
        echo "::error::arch '$ARCH' is not supported (x86_64|aarch64)"
        exit 1
        ;;
esac

read -r -a formats <<<"$FORMATS"
if [ "${#formats[@]}" -eq 0 ]; then
    echo "::error::formats must list at least one of deb, rpm"
    exit 1
fi
for f in "${formats[@]}"; do
    case "$f" in
        deb | rpm) ;;
        *)
            echo "::error::format '$f' is not supported (deb|rpm)"
            exit 1
            ;;
    esac
done

if [ ! -f "$CONFIG" ]; then
    echo "::error::nFPM config '$CONFIG' does not exist"
    exit 1
fi
if [ ! -d "$BIN_DIR" ]; then
    echo "::error::bin-dir '$BIN_DIR' does not exist"
    exit 1
fi

mkdir -p "$OUT_DIR"
out="$(cd "$OUT_DIR" && pwd)"
bin_dir="$(cd "$BIN_DIR" && pwd)"
config="$(cd "$(dirname "$CONFIG")" && pwd)/$(basename "$CONFIG")"

export PKG_BIN_DIR="$bin_dir" PKG_VERSION="$VERSION" PKG_ARCH="$pkg_arch"

assets=()
checksums=()
echo "::group::package"
for f in "${formats[@]}"; do
    asset="$out/$NAME.$f"
    nfpm package --config "$config" --packager "$f" --target "$asset"
    if [ ! -f "$asset" ]; then
        echo "::error::nfpm did not write '$asset'"
        exit 1
    fi
    if command -v sha256sum >/dev/null 2>&1; then
        (cd "$out" && sha256sum "$NAME.$f" >"$NAME.$f.sha256")
    else
        (cd "$out" && shasum -a 256 "$NAME.$f" >"$NAME.$f.sha256")
    fi
    assets+=("$asset")
    checksums+=("$asset.sha256")
done
echo "::endgroup::"

{
    echo "assets<<EOF"
    printf '%s\n' "${assets[@]}"
    echo "EOF"
    echo "checksums<<EOF"
    printf '%s\n' "${checksums[@]}"
    echo "EOF"
} >>"$GITHUB_OUTPUT"
