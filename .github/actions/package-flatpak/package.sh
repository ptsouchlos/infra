#!/usr/bin/env bash
# Build a single-file .flatpak bundle from a caller-supplied manifest and prebuilt binaries.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   MANIFEST BIN_DIR APP_ID ARCH NAME BRANCH RUNTIME_REPO OUT_DIR
# flatpak and flatpak-builder must already be installed with a flathub remote (see install.sh).
# The manifest's own directory is copied to a scratch directory and BIN_DIR is copied to bin/
# beside it, so the manifest reaches the binaries with `type: dir, path: bin` and any desktop
# file, icon or metainfo it references with a path relative to itself. Runtimes and the SDK are
# installed from flathub on demand.
# Writes asset= and checksum= to $GITHUB_OUTPUT.
set -euo pipefail

: "${MANIFEST:?MANIFEST is required}"
: "${BIN_DIR:?BIN_DIR is required}"
: "${APP_ID:?APP_ID is required}"
: "${ARCH:?ARCH is required}"
: "${NAME:?NAME is required}"
: "${BRANCH:=stable}"
: "${RUNTIME_REPO:=https://dl.flathub.org/repo/flathub.flatpakrepo}"
: "${OUT_DIR:=dist}"
: "${GITHUB_OUTPUT:=/dev/null}"

case "$ARCH" in
    x86_64 | aarch64) ;;
    *)
        echo "::error::arch '$ARCH' is not supported (x86_64|aarch64)"
        exit 1
        ;;
esac

if [ ! -f "$MANIFEST" ]; then
    echo "::error::manifest '$MANIFEST' does not exist"
    exit 1
fi
if [ ! -d "$BIN_DIR" ]; then
    echo "::error::bin-dir '$BIN_DIR' does not exist"
    exit 1
fi

mkdir -p "$OUT_DIR"
out="$(cd "$OUT_DIR" && pwd)"
manifest_dir="$(cd "$(dirname "$MANIFEST")" && pwd)"
manifest_name="$(basename "$MANIFEST")"

work="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/flatpak.XXXXXX")"
trap 'rm -rf "$work"' EXIT
mkdir "$work/src"
cp -R "$manifest_dir"/. "$work/src/"
rm -rf "$work/src/bin"
cp -R "$BIN_DIR" "$work/src/bin"

echo "::group::flatpak-builder"
# --state-dir: flatpak-builder otherwise writes .flatpak-builder into the current directory,
# which would dirty the caller's checkout.
flatpak-builder --user --force-clean --disable-rofiles-fuse \
    --state-dir="$work/state" --install-deps-from=flathub \
    --arch="$ARCH" --default-branch="$BRANCH" \
    --repo="$work/repo" "$work/build" "$work/src/$manifest_name"
echo "::endgroup::"

asset="$out/$NAME.flatpak"
echo "::group::build-bundle"
# --runtime-repo lets `flatpak install <bundle>` fetch the runtime without a pre-added remote.
flatpak build-bundle --arch="$ARCH" --runtime-repo="$RUNTIME_REPO" \
    "$work/repo" "$asset" "$APP_ID" "$BRANCH"
echo "::endgroup::"
if [ ! -f "$asset" ]; then
    echo "::error::flatpak build-bundle did not write '$asset'"
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
