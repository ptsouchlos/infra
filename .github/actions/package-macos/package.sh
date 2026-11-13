#!/usr/bin/env bash
# Assemble a .app bundle from prebuilt binaries, an Info.plist template and a PNG icon, sign it,
# and wrap it in a .dmg with an /Applications shortcut.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   BIN_DIR MERGE_BIN_DIR EXE APP_NAME BUNDLE_ID VERSION INFO_PLIST ICON NAME OUT_DIR SIGN_IDENTITY
# Runs on macOS (sips, iconutil, codesign and hdiutil), under the runner's bash 3.2: no mapfile,
# no empty-array expansion under set -u.
# Every file in BIN_DIR goes to Contents/MacOS; EXE is the bundle's main executable. INFO_PLIST
# is a template, and these placeholders are replaced:
#   @APP_NAME@ @EXECUTABLE@ @BUNDLE_ID@ @VERSION@ @SHORT_VERSION@ @ICON_FILE@
# @SHORT_VERSION@ is VERSION without a prerelease suffix (1.2.3-rc.1 -> 1.2.3), since macOS
# wants dotted numbers there. The icon must be a square PNG of at least 1024 pixels.
# SIGN_IDENTITY defaults to "-" (ad hoc, which Apple Silicon requires for a bundle to launch).
# A Developer ID identity switches on the hardened runtime and a secure timestamp.
# Writes asset= and checksum= to $GITHUB_OUTPUT.
set -euo pipefail

: "${BIN_DIR:?BIN_DIR is required}"
: "${EXE:?EXE is required}"
: "${APP_NAME:?APP_NAME is required}"
: "${BUNDLE_ID:?BUNDLE_ID is required}"
: "${VERSION:?VERSION is required}"
: "${INFO_PLIST:?INFO_PLIST is required}"
: "${ICON:?ICON is required}"
: "${NAME:?NAME is required}"
: "${OUT_DIR:=dist}"
: "${MERGE_BIN_DIR:=}"
: "${SIGN_IDENTITY:=-}"
: "${NOTARIZE:=false}"
: "${NOTARY_PROFILE:=}"
: "${NOTARY_KEY_ID:=}"
: "${NOTARY_ISSUER_ID:=}"
: "${NOTARY_KEY:=}"
: "${GITHUB_OUTPUT:=/dev/null}"

case "$NOTARIZE" in
    true | false) ;;
    *)
        echo "::error::notarize must be true or false (got '$NOTARIZE')"
        exit 1
        ;;
esac
if [ "$NOTARIZE" = true ] && [ "$SIGN_IDENTITY" = "-" ]; then
    echo "::error::notarize requires a Developer ID sign-identity (not '-')"
    exit 1
fi

if [ ! -d "$BIN_DIR" ]; then
    echo "::error::bin-dir '$BIN_DIR' does not exist"
    exit 1
fi
if [ ! -f "$BIN_DIR/$EXE" ]; then
    echo "::error::exe '$EXE' is not in bin-dir '$BIN_DIR'"
    exit 1
fi
for pair in "info-plist:$INFO_PLIST" "icon:$ICON"; do
    if [ ! -f "${pair#*:}" ]; then
        echo "::error::${pair%%:*} '${pair#*:}' does not exist"
        exit 1
    fi
done

size="$(python3 -c '
import struct, sys
with open(sys.argv[1], "rb") as f:
    head = f.read(24)
if head[:8] != b"\x89PNG\r\n\x1a\n":
    sys.exit("not a PNG")
w, h = struct.unpack(">II", head[16:24])
print(w, h)
' "$ICON")" || {
    echo "::error::icon '$ICON' is not a PNG"
    exit 1
}
read -r icon_w icon_h <<<"$size"
if [ "$icon_w" != "$icon_h" ] || [ "$icon_w" -lt 1024 ]; then
    echo "::error::icon must be a square PNG of at least 1024 pixels (got ${icon_w}x${icon_h})"
    exit 1
fi

mkdir -p "$OUT_DIR"
out="$(cd "$OUT_DIR" && pwd)"

work="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/macos-pkg.XXXXXX")"
trap 'rm -rf "$work"' EXIT
app="$work/stage/$APP_NAME.app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"

if [ -n "$MERGE_BIN_DIR" ]; then
    if [ ! -d "$MERGE_BIN_DIR" ]; then
        echo "::error::merge-bin-dir '$MERGE_BIN_DIR' does not exist"
        exit 1
    fi
    for f in "$BIN_DIR"/*; do
        base="$(basename "$f")"
        if [ ! -f "$MERGE_BIN_DIR/$base" ]; then
            echo "::error::'$base' is missing from merge-bin-dir '$MERGE_BIN_DIR'"
            exit 1
        fi
        lipo -create "$f" "$MERGE_BIN_DIR/$base" -output "$app/Contents/MacOS/$base"
    done
else
    cp "$BIN_DIR"/* "$app/Contents/MacOS/"
fi
chmod +x "$app/Contents/MacOS/"*

# Icon: the ten sizes an .iconset needs, then iconutil folds them into one .icns.
icon_file="$APP_NAME"
iconset="$work/$icon_file.iconset"
mkdir "$iconset"
make_icon() { # <pixels> <file name>
    sips -z "$1" "$1" "$ICON" --out "$iconset/$2" >/dev/null
}
make_icon 16 icon_16x16.png
make_icon 32 icon_16x16@2x.png
make_icon 32 icon_32x32.png
make_icon 64 icon_32x32@2x.png
make_icon 128 icon_128x128.png
make_icon 256 icon_128x128@2x.png
make_icon 256 icon_256x256.png
make_icon 512 icon_256x256@2x.png
make_icon 512 icon_512x512.png
make_icon 1024 icon_512x512@2x.png
iconutil -c icns "$iconset" -o "$app/Contents/Resources/$icon_file.icns"

short_version="${VERSION%%-*}"
sed -e "s|@APP_NAME@|$APP_NAME|g" \
    -e "s|@EXECUTABLE@|$EXE|g" \
    -e "s|@BUNDLE_ID@|$BUNDLE_ID|g" \
    -e "s|@VERSION@|$VERSION|g" \
    -e "s|@SHORT_VERSION@|$short_version|g" \
    -e "s|@ICON_FILE@|$icon_file|g" \
    "$INFO_PLIST" >"$app/Contents/Info.plist"

# Signing. Nested executables first, then the bundle, so the bundle's seal covers them.
# An array, because a Developer ID identity has spaces in it. Never empty, so safe on bash 3.2.
sign_args=(--force --sign "$SIGN_IDENTITY")
if [ "$SIGN_IDENTITY" != "-" ]; then
    sign_args+=(--options runtime --timestamp)
fi
echo "::group::codesign"
for binary in "$app/Contents/MacOS/"*; do
    codesign "${sign_args[@]}" "$binary"
done
codesign "${sign_args[@]}" "$app"
codesign --verify --strict "$app"
echo "::endgroup::"

if [ "$NOTARIZE" = true ]; then
    echo "::group::notarize"
    notary_zip="$work/notarize.zip"
    ditto -c -k --keepParent "$app" "$notary_zip"
    if [ -n "$NOTARY_PROFILE" ]; then
        xcrun notarytool submit "$notary_zip" --keychain-profile "$NOTARY_PROFILE" --wait
    else
        if [ -z "$NOTARY_KEY_ID" ] || [ -z "$NOTARY_ISSUER_ID" ] || [ -z "$NOTARY_KEY" ]; then
            echo "::error::notarize requires notary-profile or notary-key-id, notary-issuer-id and notary-key"
            exit 1
        fi
        if [ -f "$NOTARY_KEY" ]; then
            key_file="$NOTARY_KEY"
        else
            key_file="$work/AuthKey.p8"
            printf '%s\n' "$NOTARY_KEY" >"$key_file"
            chmod 600 "$key_file"
        fi
        xcrun notarytool submit "$notary_zip" --key "$key_file" --key-id "$NOTARY_KEY_ID" --issuer "$NOTARY_ISSUER_ID" --wait
    fi
    xcrun stapler staple "$app"
    echo "::endgroup::"
fi

# The dmg: the app beside an /Applications shortcut, so installing is one drag.
ln -s /Applications "$work/stage/Applications"
asset="$out/$NAME.dmg"
rm -f "$asset"
echo "::group::hdiutil"
hdiutil create -volname "$APP_NAME" -srcfolder "$work/stage" -ov -format UDZO "$asset"
echo "::endgroup::"
if [ ! -f "$asset" ]; then
    echo "::error::hdiutil did not write '$asset'"
    exit 1
fi
if [ "$SIGN_IDENTITY" != "-" ]; then
    codesign --force --sign "$SIGN_IDENTITY" --timestamp "$asset"
fi

base="$(basename "$asset")"
(cd "$out" && shasum -a 256 "$base" >"$base.sha256")

{
    echo "asset=$asset"
    echo "checksum=$asset.sha256"
} >>"$GITHUB_OUTPUT"
