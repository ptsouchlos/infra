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

log="$(mktemp)"
trap 'rm -f "$log"' EXIT

echo "::group::configure"
cmake "${configure[@]}" | tee "$log"
echo "::endgroup::"

# With a preset, the preset decides the binary dir; read it back from the configure output.
if [ -n "$PRESET" ]; then
    BUILD_DIR="$(sed -n 's/^-- Build files have been written to: //p' "$log" | tail -n 1 | tr -d '\r')"
    if [ -z "$BUILD_DIR" ]; then
        echo "::error::could not find the build directory of preset '$PRESET' in the configure output"
        exit 1
    fi
fi

# A build or test preset named like the configure preset takes over that step.
build_preset=false
test_preset=false
if [ -n "$PRESET" ]; then
    if (cd "$SOURCE_DIR" && cmake --build --list-presets 2>/dev/null) | grep -qF "\"$PRESET\""; then
        build_preset=true
    fi
    if (cd "$SOURCE_DIR" && ctest --list-presets 2>/dev/null) | grep -qF "\"$PRESET\""; then
        test_preset=true
    fi
fi

echo "::group::build"
if [ "$build_preset" = true ]; then
    (cd "$SOURCE_DIR" && cmake --build --preset "$PRESET")
else
    cmake --build "$BUILD_DIR" --config "$BUILD_TYPE"
fi
echo "::endgroup::"

if [ "$RUN_TESTS" = true ]; then
    echo "::group::test"
    if [ "$test_preset" = true ]; then
        (cd "$SOURCE_DIR" && ctest --preset "$PRESET")
    else
        ctest --test-dir "$BUILD_DIR" --build-config "$BUILD_TYPE" --output-on-failure
    fi
    echo "::endgroup::"
fi

if [ -n "$INSTALL_PREFIX" ]; then
    echo "::group::install"
    cmake --install "$BUILD_DIR" --config "$BUILD_TYPE" --prefix "$INSTALL_PREFIX"
    echo "::endgroup::"
fi
