#!/usr/bin/env bash
# Install a C++ toolchain on a GitHub runner and export CC/CXX.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   COMPILER (gcc|clang|appleclang|msvc), VERSION, CMAKE_VERSION, RUNNER_OS, GITHUB_ENV
#   DRY_RUN=1 prints the commands instead of running them.
set -euo pipefail

: "${COMPILER:?COMPILER is required}"
: "${RUNNER_OS:?RUNNER_OS is required}"
: "${VERSION:=}"
: "${CMAKE_VERSION:=}"
: "${GITHUB_ENV:=/dev/null}"
: "${DRY_RUN:=0}"

run() {
    if [ "$DRY_RUN" = 1 ]; then
        echo "+ $*"
    else
        "$@"
    fi
}

case "$RUNNER_OS:$COMPILER" in
    Linux:gcc | Linux:clang | macOS:appleclang | Windows:msvc) ;;
    *)
        echo "::error::compiler '$COMPILER' is not supported on $RUNNER_OS (Linux: gcc|clang, macOS: appleclang, Windows: msvc)"
        exit 1
        ;;
esac

suffix=""
if [ -n "$VERSION" ]; then
    suffix="-$VERSION"
fi

case "$RUNNER_OS:$COMPILER" in
    Linux:gcc)
        run sudo apt-get update
        run sudo apt-get install -y "gcc$suffix" "g++$suffix"
        {
            echo "CC=gcc$suffix"
            echo "CXX=g++$suffix"
        } >>"$GITHUB_ENV"
        ;;
    Linux:clang)
        run sudo apt-get update
        run sudo apt-get install -y "clang$suffix"
        {
            echo "CC=clang$suffix"
            echo "CXX=clang++$suffix"
        } >>"$GITHUB_ENV"
        ;;
    macOS:appleclang)
        {
            echo "CC=clang"
            echo "CXX=clang++"
        } >>"$GITHUB_ENV"
        ;;
    Windows:msvc)
        # The action's ilammy/msvc-dev-cmd step sets up the environment.
        ;;
esac

# Runner images ship CMake and Ninja; install only what is missing or pinned.
# PIP_BREAK_SYSTEM_PACKAGES covers Ubuntu's externally managed system Python.
python_bin="$(command -v python3 || command -v python || true)"
pip_args=()
if [ -n "$CMAKE_VERSION" ]; then
    pip_args+=("cmake==$CMAKE_VERSION")
fi
if ! command -v ninja >/dev/null 2>&1; then
    pip_args+=(ninja)
fi
if [ "${#pip_args[@]}" -gt 0 ]; then
    if [ -z "$python_bin" ] && [ "$DRY_RUN" != 1 ]; then
        echo "::error::python is required to install ${pip_args[*]}"
        exit 1
    fi
    PIP_BREAK_SYSTEM_PACKAGES=1 run "${python_bin:-python3}" -m pip install --upgrade "${pip_args[@]}"
fi
