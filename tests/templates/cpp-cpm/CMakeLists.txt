cmake_minimum_required(VERSION 3.25)
list(APPEND CMAKE_MODULE_PATH "@INFRA_DIR@/cpp/cmake")
include(prevent_in_source_builds)

project(@PROJECT_NAME@ VERSION 1.0.0 LANGUAGES CXX)

include(cpm)

CPMAddPackage(
  NAME fmt
  GITHUB_REPOSITORY fmtlib/fmt
  GIT_TAG 11.0.2
  OPTIONS "FMT_INSTALL OFF"
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

enable_testing()
add_executable(app src/main.cpp)
target_link_libraries(app PRIVATE fmt::fmt)
add_test(NAME app COMMAND app)
