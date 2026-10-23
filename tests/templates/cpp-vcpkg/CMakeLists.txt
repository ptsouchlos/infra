cmake_minimum_required(VERSION 3.25)
project(@PROJECT_NAME@ VERSION 1.0.0 LANGUAGES CXX)

# No CMAKE_MODULE_PATH here: the infra toolchain file vcpkg chainloads adds cpp/cmake.
include(project_settings)

find_package(fmt CONFIG REQUIRED)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

enable_testing()
add_executable(app src/main.cpp)
target_link_libraries(app PRIVATE fmt::fmt)
add_test(NAME app COMMAND app)
