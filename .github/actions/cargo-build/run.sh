#!/usr/bin/env bash
# Build and test through infra's cargo.just recipes.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   WORKING_DIRECTORY BUILD_TYPE RUN_TESTS BIN ARGS
set -euo pipefail

: "${WORKING_DIRECTORY:=.}"
: "${BUILD_TYPE:=debug}"
: "${RUN_TESTS:=true}"
: "${BIN:=}"
: "${ARGS:=}"

case "$BUILD_TYPE" in
    debug) build_recipe=build; test_flags=() ;;
    release) build_recipe=build-release; test_flags=(--release) ;;
    *)
        echo "::error::build-type must be debug or release, got '$BUILD_TYPE'" >&2
        exit 1
        ;;
esac

cd "$WORKING_DIRECTORY"

if ! command -v just >/dev/null; then
    echo "::error::just is not installed; run setup-rust with just: true first" >&2
    exit 1
fi
for recipe in "$build_recipe" test; do
    if ! just --show "$recipe" >/dev/null 2>&1; then
        echo "::error::no '$recipe' recipe in the justfile; import infra/rust/just/cargo.just" >&2
        exit 1
    fi
done

# BIN limits build and run to one binary (cargo.just reads CARGO_BIN); it is not a test argument.
if [ -n "$BIN" ]; then
    export CARGO_BIN="$BIN"
fi

args=()
if [ -n "$ARGS" ]; then
    read -r -a args <<<"$ARGS"
fi

echo "::group::build ($BUILD_TYPE)"
just "$build_recipe" ${args[@]+"${args[@]}"}
echo "::endgroup::"

if [ "$RUN_TESTS" = true ]; then
    echo "::group::test ($BUILD_TYPE)"
    just test ${test_flags[@]+"${test_flags[@]}"} ${args[@]+"${args[@]}"}
    echo "::endgroup::"
fi
