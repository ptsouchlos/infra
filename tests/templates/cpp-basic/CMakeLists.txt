cmake_minimum_required(VERSION 3.25)
list(APPEND CMAKE_MODULE_PATH "@INFRA_DIR@/cpp/cmake")
include(prevent_in_source_builds)

project(@PROJECT_NAME@ VERSION 1.0.0 LANGUAGES CXX)

include(project_settings)
include(compiler_warnings)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(pt_warnings INTERFACE)
pt_set_project_warnings(pt_warnings ON "" "" "" "")

add_library(core STATIC src/lib.cpp)
target_include_directories(core PUBLIC src)
target_link_libraries(core PRIVATE pt_warnings)

add_executable(app src/main.cpp)
target_link_libraries(app PRIVATE core pt_warnings)

enable_testing()
add_executable(check test/check.cpp)
target_link_libraries(check PRIVATE core pt_warnings)
add_test(NAME check COMMAND check)
