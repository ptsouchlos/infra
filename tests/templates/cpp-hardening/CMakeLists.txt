cmake_minimum_required(VERSION 3.25)
list(APPEND CMAKE_MODULE_PATH "@INFRA_DIR@/cpp/cmake")
include(prevent_in_source_builds)

project(@PROJECT_NAME@ VERSION 1.0.0 LANGUAGES CXX)

include(project_settings)
include(hardening)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Global hardening applies only to targets created after this call.
add_library(pt_options INTERFACE)
pt_enable_hardening(pt_options ON OFF)

add_library(core STATIC src/lib.cpp)
target_include_directories(core PUBLIC src)

enable_testing()
add_executable(check test/check.cpp)
target_link_libraries(check PRIVATE core)
add_test(NAME check COMMAND check)
