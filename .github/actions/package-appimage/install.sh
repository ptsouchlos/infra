#!/usr/bin/env bash
# Install a pinned appimagetool on a Linux runner, verified against a known sha256.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   TOOL_VERSION, TOOL_SHA256 (optional override), INSTALL_DIR (default $RUNNER_TEMP/appimagetool),
#   RUNNER_ARCH
#   DRY_RUN=1 prints the download URL instead of fetching it.
# Installs an `appimagetool` wrapper that runs the AppImage without FUSE (extract-and-run),
# appends INSTALL_DIR to $GITHUB_PATH and exports APPIMAGE_RUNTIME_DIR (pinned runtimes) to
# $GITHUB_ENV.
set -euo pipefail

: "${TOOL_VERSION:?TOOL_VERSION is required}"
: "${TOOL_SHA256:=}"
: "${INSTALL_DIR:=${RUNNER_TEMP:-${TMPDIR:-/tmp}}/appimagetool}"
: "${RUNNER_ARCH:=}"
: "${GITHUB_PATH:=/dev/null}"
: "${DRY_RUN:=0}"
# The runtime baked into each image; its checksums are in the loop below.
RUNTIME_VERSION=20251108

if [ -z "$RUNNER_ARCH" ]; then
    case "$(uname -m)" in
        x86_64 | amd64) RUNNER_ARCH=X64 ;;
        aarch64 | arm64) RUNNER_ARCH=ARM64 ;;
    esac
fi
case "$RUNNER_ARCH" in
    X64) arch=x86_64 ;;
    ARM64) arch=aarch64 ;;
    *)
        echo "::error::appimagetool has no Linux build for runner architecture '$RUNNER_ARCH'"
        exit 1
        ;;
esac

# Checksums of the upstream release assets, so the default pin is verified without trusting the
# download alone. Any other version needs TOOL_SHA256.
if [ -z "$TOOL_SHA256" ]; then
    case "$TOOL_VERSION/$arch" in
        1.9.1/x86_64) TOOL_SHA256=ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0 ;;
        1.9.1/aarch64) TOOL_SHA256=f0837e7448a0c1e4e650a93bb3e85802546e60654ef287576f46c71c126a9158 ;;
        *)
            echo "::error::no known checksum for appimagetool $TOOL_VERSION ($arch); set appimagetool-sha256"
            exit 1
            ;;
    esac
fi

url="https://github.com/AppImage/appimagetool/releases/download/${TOOL_VERSION}/appimagetool-${arch}.AppImage"

if [ "$DRY_RUN" = 1 ]; then
    echo "+ $url"
    echo "+ sha256 $TOOL_SHA256"
    exit 0
fi

mkdir -p "$INSTALL_DIR/runtime"
curl -fsSL --retry 3 -o "$INSTALL_DIR/appimagetool.AppImage" "$url"
echo "$TOOL_SHA256  $INSTALL_DIR/appimagetool.AppImage" | sha256sum -c -
chmod +x "$INSTALL_DIR/appimagetool.AppImage"

# appimagetool would otherwise download whatever type2-runtime "continuous" is at build time.
# Pin the runtime for both architectures; package.sh passes the one matching its ARCH.
runtime_base="https://github.com/AppImage/type2-runtime/releases/download/$RUNTIME_VERSION"
for a in x86_64 aarch64; do
    case "$a" in
        x86_64) sum=2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d ;;
        aarch64) sum=00cbdfcf917cc6c0ff6d3347d59e0ca1f7f45a6df1a428a0d6d8a78664d87444 ;;
    esac
    curl -fsSL --retry 3 -o "$INSTALL_DIR/runtime/runtime-$a" "$runtime_base/runtime-$a"
    echo "$sum  $INSTALL_DIR/runtime/runtime-$a" | sha256sum -c -
done
echo "APPIMAGE_RUNTIME_DIR=$INSTALL_DIR/runtime" >>"${GITHUB_ENV:-/dev/null}"

# Runners have no FUSE, so every AppImage here runs by extracting itself first.
cat >"$INSTALL_DIR/appimagetool" <<EOF
#!/usr/bin/env bash
exec env APPIMAGE_EXTRACT_AND_RUN=1 "$INSTALL_DIR/appimagetool.AppImage" "\$@"
EOF
chmod +x "$INSTALL_DIR/appimagetool"

echo "$INSTALL_DIR" >>"$GITHUB_PATH"
