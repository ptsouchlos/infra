# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
# Adapted from bemanproject/infra cmake/BuildTelemetry{,Config}.cmake
#
# Including this file enables CMake build instrumentation (CMake >= 4.3).
# Traces are copied to <build>/.trace by telemetry.sh; nothing leaves the machine.
include_guard(GLOBAL)

set(PT_BUILD_TELEMETRY_DIR ${CMAKE_CURRENT_LIST_DIR})

function(pt_configure_build_telemetry)
    if(NOT PT_BUILD_TELEMETRY_CONFIGURATION)
        # Check if the CMake version is at least 4.3
        if(CMAKE_VERSION VERSION_LESS "4.3")
            message(
                STATUS
                "CMake version is less than 4.3, configuring cmake_instrumentation is unavailable."
            )
            return()
        else()
            message(STATUS "Configuring Build Telemetry")
        endif()

        # Find bash and jq for the telemetry callback script.
        # On Windows, Git for Windows provides bash if available.
        find_program(PT_BASH bash)
        find_program(PT_JQ jq)
        if(NOT PT_BASH OR NOT PT_JQ)
            message(
                STATUS
                "bash or jq not found, build telemetry disabled on this platform."
            )
            return()
        endif()

        # Telemetry query
        cmake_instrumentation(
            API_VERSION 1
            DATA_VERSION 1
            OPTIONS staticSystemInformation dynamicSystemInformation trace
            HOOKS
                postGenerate
                preBuild
                postBuild
                preCMakeBuild
                postCMakeBuild
                postCMakeInstall
                postCTest
            CALLBACK ${PT_BASH}
            ${PT_BUILD_TELEMETRY_DIR}/telemetry.sh
        )
        message(
            DEBUG
            "using callback script ${PT_BUILD_TELEMETRY_DIR}/telemetry.sh via ${PT_BASH}"
        )

        # Mark configuration as done in cache
        set(PT_BUILD_TELEMETRY_CONFIGURATION
            TRUE
            CACHE INTERNAL
            "Flag to ensure Build Telemetry configured only once"
        )
    endif()
endfunction(pt_configure_build_telemetry)

pt_configure_build_telemetry()
