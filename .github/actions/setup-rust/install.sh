#!/usr/bin/env bash
# Install a Rust toolchain with rustup, plus extra components and targets.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   TOOLCHAIN, COMPONENTS, TARGETS (space-separated), RUNNER_OS
#   DRY_RUN=1 prints the commands instead of running them.
set -euo pipefail

: "${TOOLCHAIN:?TOOLCHAIN is required}"
: "${COMPONENTS:=}"
: "${TARGETS:=}"
: "${RUNNER_OS:=}"
: "${DRY_RUN:=0}"

run() {
    if [ "$DRY_RUN" = 1 ]; then
        echo "+ $*"
    else
        "$@"
    fi
}

args=()
for c in $COMPONENTS; do
    args+=(--component "$c")
done

musl=0
for t in $TARGETS; do
    args+=(--target "$t")
    case "$t" in
        *-musl) musl=1 ;;
    esac
done

if [ "$musl" = 1 ] && [ "$RUNNER_OS" = Linux ]; then
    run sudo apt-get update
    run sudo apt-get install -y musl-tools
fi

if [ "${#args[@]}" -gt 0 ]; then
    run rustup toolchain install "$TOOLCHAIN" --profile minimal --no-self-update "${args[@]}"
else
    run rustup toolchain install "$TOOLCHAIN" --profile minimal --no-self-update
fi
run rustup default "$TOOLCHAIN"
