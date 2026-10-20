#!/usr/bin/env bash
# Run cargo fmt --check, clippy and tests.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   WORKING_DIRECTORY RUN_FMT RUN_CLIPPY CLIPPY_ARGS RUN_TESTS ARGS
set -euo pipefail

: "${WORKING_DIRECTORY:=.}"
: "${RUN_FMT:=true}"
: "${RUN_CLIPPY:=true}"
: "${CLIPPY_ARGS=-D warnings}"  # only when unset: clippy-args: "" means no lint flags
: "${RUN_TESTS:=true}"
: "${ARGS:=}"

cd "$WORKING_DIRECTORY"

# ARGS goes to clippy and test only: cargo fmt rejects flags like --all-features.
args=()
if [ -n "$ARGS" ]; then
    read -r -a args <<<"$ARGS"
fi
clippy_args=()
if [ -n "$CLIPPY_ARGS" ]; then
    read -r -a clippy_args <<<"$CLIPPY_ARGS"
fi

if [ "$RUN_FMT" = true ]; then
    echo "::group::fmt"
    cargo fmt --all --check
    echo "::endgroup::"
fi

if [ "$RUN_CLIPPY" = true ]; then
    echo "::group::clippy"
    cargo clippy --all-targets ${args[@]+"${args[@]}"} -- ${clippy_args[@]+"${clippy_args[@]}"}
    echo "::endgroup::"
fi

if [ "$RUN_TESTS" = true ]; then
    echo "::group::test"
    cargo test ${args[@]+"${args[@]}"}
    echo "::endgroup::"
fi
