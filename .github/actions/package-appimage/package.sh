#!/usr/bin/env bash
# Assemble an AppDir from prebuilt binaries, a desktop file and an icon, and build an AppImage.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   BIN_DIR EXE DESKTOP_FILE ICON NAME ARCH OUT_DIR (and optionally APPRUN METAINFO
#   APPIMAGE_RUNTIME_DIR, the directory of pinned runtime-<arch> files install.sh exports)
# appimagetool must already be on PATH (see install.sh). Every file in BIN_DIR goes to usr/bin;
# EXE is the one the default AppRun starts. The desktop file's Icon= names the icon, which must be
# a PNG. APPRUN replaces the default AppRun; it is copied as-is.
# Writes asset= and checksum= to $GITHUB_OUTPUT.
set -euo pipefail

: "${BIN_DIR:?BIN_DIR is required}"
: "${EXE:?EXE is required}"
: "${DESKTOP_FILE:?DESKTOP_FILE is required}"
: "${ICON:?ICON is required}"
: "${NAME:?NAME is required}"
: "${ARCH:?ARCH is required}"
: "${APPRUN:=}"
: "${METAINFO:=}"
: "${OUT_DIR:=dist}"
: "${GITHUB_OUTPUT:=/dev/null}"

case "$ARCH" in
    x86_64 | aarch64) ;;
    *)
        echo "::error::arch '$ARCH' is not supported (x86_64|aarch64)"
        exit 1
        ;;
esac

require_file() {
    if [ ! -f "$2" ]; then
        echo "::error::$1 '$2' does not exist"
        exit 1
    fi
}
require_file "desktop-file" "$DESKTOP_FILE"
require_file "icon" "$ICON"
[ -z "$APPRUN" ] || require_file "apprun" "$APPRUN"
[ -z "$METAINFO" ] || require_file "metainfo" "$METAINFO"
if [ ! -d "$BIN_DIR" ]; then
    echo "::error::bin-dir '$BIN_DIR' does not exist"
    exit 1
fi
if [ ! -f "$BIN_DIR/$EXE" ]; then
    echo "::error::exe '$EXE' is not in bin-dir '$BIN_DIR'"
    exit 1
fi

icon_name="$(sed -n 's/^Icon=//p' "$DESKTOP_FILE" | head -n1 | tr -d '\r')"
if [ -z "$icon_name" ]; then
    echo "::error::the desktop file has no Icon= line"
    exit 1
fi

mkdir -p "$OUT_DIR"
out="$(cd "$OUT_DIR" && pwd)"

work="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/appimage.XXXXXX")"
trap 'rm -rf "$work"' EXIT
appdir="$work/App.AppDir"
mkdir -p "$appdir/usr/bin" "$appdir/usr/share/applications" "$appdir/usr/share/metainfo"

cp "$BIN_DIR"/* "$appdir/usr/bin/"
chmod +x "$appdir/usr/bin/"*

cp "$DESKTOP_FILE" "$appdir/usr/share/applications/$(basename "$DESKTOP_FILE")"
cp "$DESKTOP_FILE" "$appdir/$(basename "$DESKTOP_FILE")"

# appimagetool wants the icon at the AppDir root; hicolor makes it visible to desktop integration.
cp "$ICON" "$appdir/$icon_name.png"
cp "$ICON" "$appdir/.DirIcon"
size="$(python3 -c '
import struct, sys
with open(sys.argv[1], "rb") as f:
    head = f.read(24)
if head[:8] != b"\x89PNG\r\n\x1a\n":
    sys.exit("not a PNG")
w, h = struct.unpack(">II", head[16:24])
print(f"{w}x{h}")
' "$ICON")"
mkdir -p "$appdir/usr/share/icons/hicolor/$size/apps"
cp "$ICON" "$appdir/usr/share/icons/hicolor/$size/apps/$icon_name.png"

if [ -n "$METAINFO" ]; then
    cp "$METAINFO" "$appdir/usr/share/metainfo/$(basename "$METAINFO")"
fi

if [ -n "$APPRUN" ]; then
    cp "$APPRUN" "$appdir/AppRun"
else
    sed "s|@EXE@|$EXE|g" "$(dirname "${BASH_SOURCE[0]}")/AppRun" >"$appdir/AppRun"
fi
chmod +x "$appdir/AppRun"

asset="$out/$NAME.AppImage"
args=()
[ -n "$METAINFO" ] || args+=(--no-appstream)
# Use the runtime pinned by install.sh instead of letting appimagetool download "continuous".
if [ -n "${APPIMAGE_RUNTIME_DIR:-}" ]; then
    args+=(--runtime-file "$APPIMAGE_RUNTIME_DIR/runtime-$ARCH")
fi
echo "::group::package"
# ${args[@]+...}: an empty array is an unbound variable under set -u in bash < 4.4 (macOS).
ARCH="$ARCH" appimagetool ${args[@]+"${args[@]}"} "$appdir" "$asset"
echo "::endgroup::"
if [ ! -f "$asset" ]; then
    echo "::error::appimagetool did not write '$asset'"
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
