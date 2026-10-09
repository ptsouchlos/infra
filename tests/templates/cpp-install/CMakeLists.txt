cmake_minimum_required(VERSION 3.25)
list(APPEND CMAKE_MODULE_PATH "@INFRA_DIR@/cpp/cmake")
include(prevent_in_source_builds)

project(@PROJECT_NAME@ VERSION 1.0.0 LANGUAGES CXX)

include(install_library)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(foo.bar STATIC src/lib.cpp)
target_sources(
  foo.bar
  PUBLIC FILE_SET HEADERS BASE_DIRS src FILES src/lib.hpp
)

pt_install_library(foo.bar TARGETS foo.bar)
