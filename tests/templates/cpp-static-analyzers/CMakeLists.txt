cmake_minimum_required(VERSION 3.25)
list(APPEND CMAKE_MODULE_PATH "@INFRA_DIR@/cpp/cmake")
include(prevent_in_source_builds)

project(@PROJECT_NAME@ VERSION 1.0.0 LANGUAGES CXX)

include(project_settings)
include(static_analyzers)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# The macros set global CMAKE_CXX_* variables that only affect targets created afterwards,
# so they run before core exists (clang-tidy is handed the name of that later target).
pt_enable_cppcheck(OFF "")
pt_enable_include_what_you_use()
pt_enable_clang_tidy(core OFF)

add_library(core STATIC src/lib.cpp)
target_include_directories(core PUBLIC src)

enable_testing()
add_executable(check test/check.cpp)
target_link_libraries(check PRIVATE core)
add_test(NAME check COMMAND check)
