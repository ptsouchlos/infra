#!/usr/bin/env bash
# Configure, build, test and optionally install a CMake project.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   SOURCE_DIR BUILD_DIR BUILD_TYPE PRESET CONFIGURE_ARGS RUN_TESTS INSTALL_PREFIX CCACHE
set -euo pipefail

: "${SOURCE_DIR:=.}"
: "${BUILD_DIR:=build}"
: "${BUILD_TYPE:=Release}"
: "${PRESET:=}"
: "${CONFIGURE_ARGS:=}"
: "${RUN_TESTS:=true}"
: "${INSTALL_PREFIX:=}"
: "${CCACHE:=false}"

configure=()
if [ -n "$PRESET" ]; then
    configure+=(-S "$SOURCE_DIR" --preset "$PRESET")
else
    configure+=(-S "$SOURCE_DIR" -B "$BUILD_DIR" -G Ninja "-DCMAKE_BUILD_TYPE=$BUILD_TYPE")
fi
if [ "$CCACHE" = true ]; then
    configure+=(-DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache)
fi
if [ -n "$CONFIGURE_ARGS" ]; then
    read -r -a extra <<<"$CONFIGURE_ARGS"
    configure+=("${extra[@]}")
fi

echo "::group::configure"
cmake "${configure[@]}"
echo "::endgroup::"

# With a preset, the preset decides the binary dir; build/test/install must use the same one.
if [ ! -f "$BUILD_DIR/CMakeCache.txt" ]; then
    echo "::error::no CMakeCache.txt in '$BUILD_DIR' after configure; build-dir must match the preset's binaryDir"
    exit 1
fi

echo "::group::build"
cmake --build "$BUILD_DIR" --config "$BUILD_TYPE"
echo "::endgroup::"

if [ "$RUN_TESTS" = true ]; then
    echo "::group::test"
    ctest --test-dir "$BUILD_DIR" --build-config "$BUILD_TYPE" --output-on-failure
    echo "::endgroup::"
fi

if [ -n "$INSTALL_PREFIX" ]; then
    echo "::group::install"
    cmake --install "$BUILD_DIR" --config "$BUILD_TYPE" --prefix "$INSTALL_PREFIX"
    echo "::endgroup::"
fi
