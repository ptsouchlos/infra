#!/usr/bin/env bash
# Install a C++ toolchain on a GitHub runner and export CC/CXX.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   COMPILER (gcc|clang|appleclang|msvc), VERSION, CMAKE_VERSION, VCPKG, RUNNER_OS, GITHUB_ENV
#   DRY_RUN=1 prints the commands instead of running them.
set -euo pipefail

: "${COMPILER:?COMPILER is required}"
: "${RUNNER_OS:?RUNNER_OS is required}"
: "${VERSION:=}"
: "${CMAKE_VERSION:=}"
: "${VCPKG:=false}"
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
    Linux:gcc | Linux:clang | macOS:appleclang | Windows:msvc | Windows:clang) ;;
    *)
        echo "::error::compiler '$COMPILER' is not supported on $RUNNER_OS (Linux: gcc|clang, macOS: appleclang, Windows: msvc|clang)"
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
    Windows:clang)
        # LLVM ships on the runner and targets the MSVC runtime, which the msvc-dev-cmd step provides.
        {
            echo "CC=clang"
            echo "CXX=clang++"
        } >>"$GITHUB_ENV"
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

# vcpkg: keep a VCPKG_ROOT the job already set, otherwise clone and bootstrap a fresh one. The
# runner images' own copy is not used: it can predate a manifest's builtin-baseline, and macOS
# images do not ship it.
if [ "$VCPKG" = true ]; then
    root="${VCPKG_ROOT:-}"
    if [ -z "$root" ]; then
        root="${RUNNER_TEMP:-/tmp}/vcpkg"
        run git clone https://github.com/microsoft/vcpkg.git "$root"
        if [ "$RUNNER_OS" = Windows ]; then
            bat="$root/bootstrap-vcpkg.bat"
            if command -v cygpath >/dev/null 2>&1; then
                bat="$(cygpath -w "$bat")"
            fi
            run cmd.exe //c "$bat" -disableMetrics
        else
            run "$root/bootstrap-vcpkg.sh" -disableMetrics
        fi
    fi
    # CMake reads $env{VCPKG_ROOT} on Windows too, so hand it a C:/... path, not /c/...
    if command -v cygpath >/dev/null 2>&1; then
        root="$(cygpath -m "$root")"
    fi
    echo "VCPKG_ROOT=$root" >>"$GITHUB_ENV"
fi
