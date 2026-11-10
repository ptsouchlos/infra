#!/usr/bin/env bash
# Install a pinned nFPM release on a Linux runner, verified against the release's checksums.txt.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   NFPM_VERSION (without the leading v), INSTALL_DIR (default $RUNNER_TEMP/nfpm), RUNNER_ARCH
#   DRY_RUN=1 prints the download URLs instead of fetching them.
# Appends INSTALL_DIR to $GITHUB_PATH.
set -euo pipefail

: "${NFPM_VERSION:?NFPM_VERSION is required}"
: "${INSTALL_DIR:=${RUNNER_TEMP:-${TMPDIR:-/tmp}}/nfpm}"
: "${RUNNER_ARCH:=}"
: "${GITHUB_PATH:=/dev/null}"
: "${DRY_RUN:=0}"

if [ -z "$RUNNER_ARCH" ]; then
    case "$(uname -m)" in
        x86_64 | amd64) RUNNER_ARCH=X64 ;;
        aarch64 | arm64) RUNNER_ARCH=ARM64 ;;
    esac
fi
case "$RUNNER_ARCH" in
    X64) suffix=x86_64 ;;
    ARM64) suffix=arm64 ;;
    *)
        echo "::error::nFPM has no Linux build for runner architecture '$RUNNER_ARCH'"
        exit 1
        ;;
esac

file="nfpm_${NFPM_VERSION}_Linux_${suffix}.tar.gz"
base="https://github.com/goreleaser/nfpm/releases/download/v${NFPM_VERSION}"

if [ "$DRY_RUN" = 1 ]; then
    echo "+ $base/$file"
    echo "+ $base/checksums.txt"
    exit 0
fi

mkdir -p "$INSTALL_DIR"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

curl -fsSL --retry 3 -o "$work/$file" "$base/$file"
curl -fsSL --retry 3 -o "$work/checksums.txt" "$base/checksums.txt"
(cd "$work" && awk -v f="$file" '$2 == f' checksums.txt | sha256sum -c -)

tar -C "$INSTALL_DIR" -xzf "$work/$file" nfpm
echo "$INSTALL_DIR" >>"$GITHUB_PATH"
"$INSTALL_DIR/nfpm" --version
