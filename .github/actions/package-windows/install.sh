#!/usr/bin/env bash
# Install a pinned WiX Toolset (the `wix` dotnet tool, v4 or later) on a Windows runner.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   WIX_VERSION, INSTALL_DIR (default $RUNNER_TEMP/wix)
#   DRY_RUN=1 prints the command instead of running it.
# Appends INSTALL_DIR to $GITHUB_PATH. The dotnet SDK is preinstalled on GitHub's runners.
set -euo pipefail

: "${WIX_VERSION:?WIX_VERSION is required}"
: "${INSTALL_DIR:=${RUNNER_TEMP:-${TMPDIR:-/tmp}}/wix}"
: "${GITHUB_PATH:=/dev/null}"
: "${DRY_RUN:=0}"

if [ "$DRY_RUN" = 1 ]; then
    echo "+ dotnet tool install wix --version $WIX_VERSION --tool-path $INSTALL_DIR"
    exit 0
fi

dotnet tool install wix --version "$WIX_VERSION" --tool-path "$INSTALL_DIR"
if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$INSTALL_DIR" >>"$GITHUB_PATH"
else
    echo "$INSTALL_DIR" >>"$GITHUB_PATH"
fi
"$INSTALL_DIR/wix" --version
