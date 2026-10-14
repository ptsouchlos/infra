cmake_minimum_required(VERSION 3.30)
list(APPEND CMAKE_MODULE_PATH "@INFRA_DIR@/cpp/cmake")
include(enable_import_std)   # must precede project(): it sets the experimental-feature UUID

project(@PROJECT_NAME@ LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_MODULE_STD ON)

add_executable(app src/main.cpp)

enable_testing()
add_test(NAME app COMMAND app)
