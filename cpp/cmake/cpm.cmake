# Adapted from cpp-best-practices/cmake_template cmake/CPM.cmake
# SPDX-License-Identifier: MIT
#
# SPDX-FileCopyrightText: Copyright (c) 2019-2023 Lars Melchior and contributors
#
# Bootstraps TheLartians/CPM.cmake. Include this file, then call CPMAddPackage().
# Override pt_CPM_VERSION / pt_CPM_HASH_SUM together to pin a different release.
# Set CPM_SOURCE_CACHE (variable or environment) to share downloads across builds.
include_guard(GLOBAL)

set(PT_CPM_VERSION "0.42.1" CACHE STRING "CPM.cmake release to bootstrap")
set(PT_CPM_HASH_SUM "f3a6dcc6a04ce9e7f51a127307fa4f699fb2bade357a8eb4c5b45df76e1dc6a5" CACHE STRING "SHA256 of the CPM.cmake release asset")

if(CPM_SOURCE_CACHE)
  set(_pt_cpm_location "${CPM_SOURCE_CACHE}/cpm/CPM_${PT_CPM_VERSION}.cmake")
elseif(DEFINED ENV{CPM_SOURCE_CACHE})
  set(_pt_cpm_location "$ENV{CPM_SOURCE_CACHE}/cpm/CPM_${PT_CPM_VERSION}.cmake")
else()
  set(_pt_cpm_location "${CMAKE_BINARY_DIR}/cmake/CPM_${PT_CPM_VERSION}.cmake")
endif()

# Expand relative paths (a leading tilde, for instance)
get_filename_component(_pt_cpm_location "${_pt_cpm_location}" ABSOLUTE)

if(NOT EXISTS "${_pt_cpm_location}")
  file(
    DOWNLOAD
    "https://github.com/cpm-cmake/CPM.cmake/releases/download/v${PT_CPM_VERSION}/CPM.cmake"
    "${_pt_cpm_location}"
    EXPECTED_HASH "SHA256=${PT_CPM_HASH_SUM}"
  )
endif()

include("${_pt_cpm_location}")
